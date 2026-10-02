"""Synthetic data generators for hospital occupancy modeling."""

from __future__ import annotations

import numpy as np
import pandas as pd


def impute_monthly_seasonal_median(values: pd.Series) -> pd.Series:
    """Replace missing monthly values with the median for that calendar month."""
    if not isinstance(values.index, pd.DatetimeIndex):
        raise TypeError("values must use a DatetimeIndex")
    if values.empty:
        raise ValueError("values must not be empty")

    numeric_values = pd.to_numeric(values, errors="coerce")
    seasonal_medians = numeric_values.groupby(numeric_values.index.month).transform(
        "median"
    )
    imputed_values = numeric_values.fillna(seasonal_medians)
    if imputed_values.isna().any():
        raise ValueError("seasonal medians could not impute every missing value")
    return imputed_values


def round_preserving_total(raw_values: pd.Series, total: int) -> pd.Series:
    """Round values to integers using largest-remainder rounding so they sum to total."""
    floor_values = np.floor(raw_values)
    remainder = raw_values - floor_values
    deficit = int(total - floor_values.sum())
    if deficit < 0:
        raise ValueError("total is smaller than the sum of floored values")
    result = floor_values.copy()
    for index in remainder.sort_values(ascending=False).index[:deficit]:
        result[index] += 1
    return result.astype(int)


def allocate_daily_category_beds(
    daily_totals: pd.Series, monthly_shares: pd.DataFrame
) -> pd.DataFrame:
    """Split each day's total occupied beds across categories using that month's shares.

    Categories with a missing (NaN) share for a given month are left as NaN for
    every day in that month rather than fabricated, and the remaining
    categories' integer counts are reconciled to sum exactly to the day's total.
    """
    daily_totals = daily_totals.sort_index()
    months = daily_totals.index.to_period("M")
    rows = []
    for period in months.unique():
        month_start = period.start_time
        shares_row = monthly_shares.loc[month_start].dropna()
        for date in daily_totals.index[months == period]:
            total = int(daily_totals.loc[date])
            allocated = round_preserving_total(shares_row * total, total)
            row = pd.Series(np.nan, index=monthly_shares.columns, name=date)
            row[allocated.index] = allocated
            rows.append(row)
    return pd.DataFrame(rows).sort_index()


def generate_daily_bed_turnover(
    daily_los: pd.Series,
    monthly_target: pd.Series,
    seed: int,
    capacity: float | None = None,
) -> pd.DataFrame:
    """Generate daily occupied beds via an admissions/discharges turnover recurrence.

    Each day's discharges are the previous day's occupied beds divided by that
    day's length of stay (so longer stays discharge a smaller fraction of
    patients). Admissions are Poisson-distributed around the rate needed to
    sustain that month's target census at the current LOS, which keeps the
    series mean-reverting without forcing an exact monthly match.
    """
    if not isinstance(daily_los.index, pd.DatetimeIndex):
        raise TypeError("daily_los must use a DatetimeIndex")
    if not isinstance(monthly_target.index, pd.DatetimeIndex):
        raise TypeError("monthly_target must use a DatetimeIndex")
    if daily_los.empty:
        raise ValueError("daily_los must not be empty")
    if daily_los.isna().any() or (daily_los <= 0).any():
        raise ValueError("daily_los must be positive and non-missing")

    daily_los = daily_los.sort_index()
    rng = np.random.default_rng(seed)
    occupied_previous: float | None = None
    rows = []

    for date, los_days in daily_los.items():
        month_start = date.to_period("M").start_time
        target_mean = float(monthly_target.loc[month_start])
        if occupied_previous is None:
            occupied_previous = target_mean

        expected_admissions = target_mean / los_days
        admissions = rng.poisson(expected_admissions) if expected_admissions > 0 else 0
        discharges = occupied_previous / los_days
        occupied_continuous = max(occupied_previous - discharges + admissions, 0.0)
        if capacity is not None:
            occupied_continuous = min(occupied_continuous, capacity)

        rows.append({
            "date": date,
            "monthly_target_census": target_mean,
            "los_days": los_days,
            "expected_admissions_per_day": expected_admissions,
            "admissions": admissions,
            "expected_discharges": discharges,
            "occupied_beds_continuous": occupied_continuous,
        })
        occupied_previous = occupied_continuous

    result = pd.DataFrame(rows)
    result["occupied_beds"] = result["occupied_beds_continuous"].round().astype(int)
    return result


def generate_daily_length_of_stay(
    monthly_means: pd.Series,
    daily_cv: float,
    persistence: float,
    seed: int,
    minimum_days: float = 0.1,
) -> pd.DataFrame:
    """Generate day-to-day varying length-of-stay values that average to the monthly mean.

    Unlike occupied-bed counts, length of stay is continuous and has no natural
    capacity bound, so each month's daily values are rescaled after clipping so
    their mean exactly equals the monthly target.
    """
    if not isinstance(monthly_means.index, pd.DatetimeIndex):
        raise TypeError("monthly_means must use a DatetimeIndex")
    if daily_cv < 0:
        raise ValueError("daily_cv must be non-negative")
    if not -1 < persistence < 1:
        raise ValueError("persistence must be between -1 and 1")
    if monthly_means.empty or monthly_means.isna().any():
        raise ValueError("monthly_means must contain non-missing values")
    if (monthly_means <= 0).any():
        raise ValueError("monthly means must be positive")

    monthly_means = monthly_means.sort_index()
    if monthly_means.index.to_period("M").duplicated().any():
        raise ValueError("monthly_means must contain one value per month")

    rng = np.random.default_rng(seed)
    innovation_scale = np.sqrt(1 - persistence**2)
    previous_deviation = 0.0
    frames: list[pd.DataFrame] = []

    for month_date, monthly_mean_value in monthly_means.items():
        monthly_mean = float(monthly_mean_value)
        period = month_date.to_period("M")
        dates = pd.date_range(period.start_time, period.end_time, freq="D")

        deviations = np.empty(len(dates), dtype=float)
        for index in range(len(dates)):
            previous_deviation = (
                persistence * previous_deviation
                + innovation_scale * rng.normal()
            )
            deviations[index] = previous_deviation

        deviation_std = deviations.std(ddof=0)
        if deviation_std > 0:
            deviations = (deviations - deviations.mean()) / deviation_std
        else:
            deviations.fill(0.0)

        raw_values = np.clip(
            monthly_mean + monthly_mean * daily_cv * deviations, minimum_days, None
        )
        actual_mean = raw_values.mean()
        scale = monthly_mean / actual_mean if actual_mean > 0 else 1.0

        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "monthly_mean_los_days": monthly_mean,
                    "length_of_stay_days": raw_values * scale,
                }
            )
        )

    return pd.concat(frames, ignore_index=True)


def compute_required_nurses(
    daily_census: pd.DataFrame,
    category_to_unit: dict[str, str],
    unit_ratios: dict[str, dict[str, float]],
    shifts_per_day: int,
) -> pd.DataFrame:
    """Compute minimum/maximum nurses required per shift and per day by unit.

    ``daily_census`` has one column per category (occupied beds). Category
    census is summed into units, then each unit's census is divided by its
    patients-per-nurse ratio and rounded up. ``nurses_min`` uses the higher
    patients-per-nurse bound; ``nurses_max`` uses the lower bound.
    """
    missing = set(category_to_unit) - set(daily_census.columns)
    if missing:
        raise KeyError(f"census is missing categories: {sorted(missing)}")
    unknown_units = set(category_to_unit.values()) - set(unit_ratios)
    if unknown_units:
        raise KeyError(f"no ratio defined for units: {sorted(unknown_units)}")
    if shifts_per_day <= 0:
        raise ValueError("shifts_per_day must be positive")

    census = daily_census[list(category_to_unit)].fillna(0)
    if (census < 0).any().any():
        raise ValueError("census values must be non-negative")
    unit_census = census.T.groupby(pd.Series(category_to_unit)).sum().T

    result = pd.DataFrame(index=daily_census.index)
    for unit, ratio in unit_ratios.items():
        if unit not in unit_census.columns:
            continue
        low, high = ratio["patients_per_nurse_min"], ratio["patients_per_nurse_max"]
        if not 0 < low <= high:
            raise ValueError(f"invalid ratio bounds for {unit}")
        result[f"census_{unit}"] = unit_census[unit].astype(int)
        result[f"nurses_per_shift_min_{unit}"] = np.ceil(unit_census[unit] / high).astype(int)
        result[f"nurses_per_shift_max_{unit}"] = np.ceil(unit_census[unit] / low).astype(int)

    for bound in ("min", "max"):
        per_shift = result.filter(like=f"nurses_per_shift_{bound}_").sum(axis=1)
        result[f"nurses_per_shift_{bound}_total"] = per_shift
        result[f"nurse_shifts_per_day_{bound}_total"] = per_shift * shifts_per_day
    return result


def lognormal_params(mean: float, cv: float) -> tuple[float, float]:
    """Return (mu, sigma) of a log-normal with the given arithmetic mean and CV."""
    if mean <= 0 or cv <= 0:
        raise ValueError("mean and cv must be positive")
    sigma2 = np.log(1 + cv**2)
    return float(np.log(mean) - sigma2 / 2), float(np.sqrt(sigma2))


def sample_cleaning_minutes(
    mean_minutes: float, cv: float, size: int, seed: int
) -> np.ndarray:
    """Draw right-skewed (log-normal) cleaning durations in minutes."""
    mu, sigma = lognormal_params(mean_minutes, cv)
    return np.random.default_rng(seed).lognormal(mu, sigma, size)


def compute_daily_cleaning_workload(
    daily_census: pd.DataFrame,
    daily_discharges: pd.DataFrame,
    category_to_unit: dict[str, str],
    unit_minutes: dict[str, dict[str, float]],
    occupied_cleans_per_bed_per_day: float = 1,
) -> pd.DataFrame:
    """Compute expected daily cleaning minutes by unit from census and discharges.

    Both inputs have one column per category. Occupied-room minutes are census
    times cleans per bed times the unit's occupied-clean mean; discharge minutes
    are discharges times the unit's discharge-clean mean.
    """
    for name, frame in (("census", daily_census), ("discharges", daily_discharges)):
        missing = set(category_to_unit) - set(frame.columns)
        if missing:
            raise KeyError(f"{name} is missing categories: {sorted(missing)}")
    unknown_units = set(category_to_unit.values()) - set(unit_minutes)
    if unknown_units:
        raise KeyError(f"no cleaning minutes defined for units: {sorted(unknown_units)}")

    groups = pd.Series(category_to_unit)
    unit_census = daily_census[list(category_to_unit)].fillna(0).T.groupby(groups).sum().T
    unit_discharges = daily_discharges[list(category_to_unit)].fillna(0).T.groupby(groups).sum().T
    if (unit_census < 0).any().any() or (unit_discharges < 0).any().any():
        raise ValueError("census and discharges must be non-negative")

    result = pd.DataFrame(index=daily_census.index)
    for unit in unit_census.columns:
        minutes = unit_minutes[unit]
        result[f"discharges_{unit}"] = unit_discharges[unit]
        result[f"occupied_clean_minutes_{unit}"] = (
            unit_census[unit] * occupied_cleans_per_bed_per_day * minutes["occupied"]
        )
        result[f"discharge_clean_minutes_{unit}"] = unit_discharges[unit] * minutes["discharge"]
    result["occupied_clean_minutes_total"] = result.filter(like="occupied_clean_minutes_").sum(axis=1)
    result["discharge_clean_minutes_total"] = result.filter(like="discharge_clean_minutes_").sum(axis=1)
    result["cleaning_hours_total"] = (
        result["occupied_clean_minutes_total"] + result["discharge_clean_minutes_total"]
    ) / 60
    return result


def sample_diurnal_arrival_seconds(
    event_counts: list[int],
    seed: int,
    peak_hour: float,
    amplitude: float,
) -> np.ndarray:
    """Sample within-day event times from a smooth 24-hour sinusoidal profile.

    The output is a flat array of seconds after midnight in the same group order
    as ``event_counts``. The relative event intensity is
    ``1 + amplitude * cos(2*pi*(hour - peak_hour)/24)``; daily group counts are
    preserved exactly.
    """
    counts = np.asarray(event_counts)
    if counts.ndim != 1 or not np.issubdtype(counts.dtype, np.integer):
        raise ValueError("event_counts must be a one-dimensional sequence of integers")
    if (counts < 0).any():
        raise ValueError("event_counts must be non-negative")
    if not 0 <= peak_hour < 24:
        raise ValueError("peak_hour must be between 0 and 24")
    if not 0 <= amplitude < 1:
        raise ValueError("amplitude must be between 0 and 1")

    total = int(counts.sum())
    if total == 0:
        return np.empty(0, dtype=np.int64)

    rng = np.random.default_rng(seed)
    samples = np.empty(total, dtype=float)
    sampled = 0
    while sampled < total:
        candidate_count = max(64, 2 * (total - sampled))
        candidates = rng.uniform(0, 24, size=candidate_count)
        phase = 2 * np.pi * (candidates - peak_hour) / 24
        acceptance = (1 + amplitude * np.cos(phase)) / (1 + amplitude)
        accepted = candidates[rng.random(candidate_count) < acceptance]
        accepted_count = min(len(accepted), total - sampled)
        samples[sampled : sampled + accepted_count] = accepted[:accepted_count]
        sampled += accepted_count

    return np.floor(samples * 3600).astype(np.int64)


def assign_patient_attributes(
    appointments: pd.DataFrame,
    settings: dict,
    category_to_unit: dict[str, str],
    seed: int,
) -> pd.DataFrame:
    """Add severity, priority, moveability, deadline, and unit columns to appointments.

    ``settings`` is the ``patient_attributes`` block of ``data/assumptions.yaml``.
    Severity is drawn per category from ``severity_mix``; critical patients take
    ``critical_priority_rank``. Non-critical patients in ``scheduled_admissions``
    categories may be flagged ``is_scheduled`` and take its rank. Electives move
    within a severity-based window from their requested ``date``; non-critical
    viral patients move within the same day.
    """
    categories = set(appointments["category"])
    mix = settings["severity_mix"]
    for name, mapping in (("severity_mix", mix), ("base_priority_rank", settings["base_priority_rank"]),
                          ("category_to_unit", category_to_unit)):
        missing = categories - set(mapping)
        if missing:
            raise KeyError(f"{name} is missing categories: {sorted(missing)}")
    levels = settings["severity_levels"]
    for category, shares in mix.items():
        if set(shares) - set(levels):
            raise ValueError(f"{category} has unknown severity levels")
        if not np.isclose(sum(shares.values()), 1.0):
            raise ValueError(f"{category} severity shares must sum to 1")

    rng = np.random.default_rng(seed)
    result = appointments.copy()
    severity = pd.Series(index=result.index, dtype=object)
    for category in sorted(categories):
        rows = result.index[result["category"] == category]
        shares = mix[category]
        severity[rows] = rng.choice(list(shares), size=len(rows), p=list(shares.values()))
    result["severity"] = pd.Categorical(severity, categories=levels, ordered=True)

    is_critical = result["severity"] == "critical"
    result["priority_rank"] = result["category"].map(settings["base_priority_rank"]).astype(int)

    scheduled = settings.get("scheduled_admissions", {})
    result["is_scheduled"] = False
    for category, share in sorted(scheduled.get("share_of_non_critical", {}).items()):
        rows = result.index[(result["category"] == category) & ~is_critical]
        result.loc[rows, "is_scheduled"] = rng.random(len(rows)) < share
    if scheduled:
        result.loc[result["is_scheduled"], "priority_rank"] = int(scheduled["priority_rank"])
    result.loc[is_critical, "priority_rank"] = int(settings["critical_priority_rank"])

    moves = settings["moveability"]
    is_elective = result["category"] == "elective"
    is_viral = result["category"].isin(moves["viral_categories"])
    result["is_moveable"] = is_elective | (is_viral & ~is_critical)
    window = pd.Series(np.nan, index=result.index)
    window[is_elective] = result.loc[is_elective, "severity"].astype(str).map(
        moves["elective_move_window_days"]
    )
    window[is_viral & ~is_critical] = moves["viral_move_window_days"]
    if window[result["is_moveable"]].isna().any():
        raise ValueError("every moveable patient needs a move window")
    result["move_window_days"] = window.astype("Int64")
    result["deadline_date"] = (
        pd.to_datetime(result["date"]) + pd.to_timedelta(result["move_window_days"], unit="D")
    ).dt.date
    result["unit"] = result["category"].map(category_to_unit)
    return result


def sample_nhpp_arrival_seconds(
    daily_rate: float, peak_hour: float, amplitude: float, seed: int
) -> np.ndarray:
    """Sample one day of non-homogeneous Poisson arrivals by thinning.

    The intensity is ``daily_rate / 24 * (1 + amplitude * cos(2*pi*(hour - peak_hour)/24))``
    per hour, so the expected daily count is ``daily_rate`` and the realized count
    is Poisson. Returns sorted seconds after midnight.
    """
    if daily_rate < 0:
        raise ValueError("daily_rate must be non-negative")
    if not 0 <= peak_hour < 24:
        raise ValueError("peak_hour must be between 0 and 24")
    if not 0 <= amplitude < 1:
        raise ValueError("amplitude must be between 0 and 1")

    rng = np.random.default_rng(seed)
    candidates = rng.uniform(0, 24, size=rng.poisson(daily_rate * (1 + amplitude)))
    intensity = 1 + amplitude * np.cos(2 * np.pi * (candidates - peak_hour) / 24)
    accepted = candidates[rng.random(len(candidates)) < intensity / (1 + amplitude)]
    return np.sort(np.floor(accepted * 3600).astype(np.int64))


def generate_synthetic_day(
    date: pd.Timestamp,
    category_rates: dict[str, float],
    peak_hour: float,
    amplitude: float,
    seed: int,
) -> pd.DataFrame:
    """Generate one day of patient arrivals per category from expected daily rates.

    Returns one row per arrival with ``patient_id``, ``date``, ``category``, and
    ``arrival_time``, sorted by arrival time.
    """
    date = pd.Timestamp(date).normalize()
    seeds = np.random.SeedSequence(seed).generate_state(len(category_rates))
    frames = []
    for category_seed, (category, rate) in zip(seeds, sorted(category_rates.items())):
        seconds = sample_nhpp_arrival_seconds(rate, peak_hour, amplitude, int(category_seed))
        frames.append(pd.DataFrame({
            "patient_id": [f"{date:%Y%m%d}-{category}-{n:04d}" for n in range(1, len(seconds) + 1)],
            "date": date.date(),
            "category": category,
            "arrival_time": date + pd.to_timedelta(seconds, unit="s"),
        }))
    day = pd.concat(frames, ignore_index=True)
    return day.sort_values(["arrival_time", "patient_id"]).reset_index(drop=True)


def generate_daily_occupied_beds(
    monthly_means: pd.Series,
    capacity: int,
    daily_cv: float,
    persistence: float,
    seed: int,
) -> pd.DataFrame:
    """Generate capacity-bounded daily occupancy from monthly mean census values.

    The monthly mean supplies the seasonal level. An AR(1) process supplies
    autocorrelated day-to-day variation. Integer counts are reconciled within
    each month so their total equals the rounded monthly target patient-days.
    """
    if not isinstance(monthly_means.index, pd.DatetimeIndex):
        raise TypeError("monthly_means must use a DatetimeIndex")
    if capacity <= 0:
        raise ValueError("capacity must be positive")
    if daily_cv < 0:
        raise ValueError("daily_cv must be non-negative")
    if not -1 < persistence < 1:
        raise ValueError("persistence must be between -1 and 1")
    if monthly_means.empty or monthly_means.isna().any():
        raise ValueError("monthly_means must contain non-missing values")
    if (monthly_means < 0).any() or (monthly_means > capacity).any():
        raise ValueError("monthly means must be between zero and capacity")

    monthly_means = monthly_means.sort_index()
    if monthly_means.index.to_period("M").duplicated().any():
        raise ValueError("monthly_means must contain one value per month")

    rng = np.random.default_rng(seed)
    innovation_scale = np.sqrt(1 - persistence**2)
    previous_deviation = 0.0
    frames: list[pd.DataFrame] = []

    for month_date, monthly_mean_value in monthly_means.items():
        monthly_mean = float(monthly_mean_value)
        period = month_date.to_period("M")
        dates = pd.date_range(period.start_time, period.end_time, freq="D")

        deviations = np.empty(len(dates), dtype=float)
        for index in range(len(dates)):
            previous_deviation = (
                persistence * previous_deviation
                + innovation_scale * rng.normal()
            )
            deviations[index] = previous_deviation

        deviation_std = deviations.std(ddof=0)
        if deviation_std > 0:
            deviations = (deviations - deviations.mean()) / deviation_std
        else:
            deviations.fill(0.0)

        raw_counts = np.clip(
            monthly_mean + monthly_mean * daily_cv * deviations,
            0,
            capacity,
        )
        daily_counts = np.rint(raw_counts).astype(int)
        target_total = int(round(monthly_mean * len(dates)))
        difference = target_total - int(daily_counts.sum())

        while difference != 0:
            if difference > 0:
                candidates = np.flatnonzero(daily_counts < capacity)
                priorities = raw_counts[candidates] - daily_counts[candidates]
                ordered = candidates[np.argsort(priorities)[::-1]]
                adjustment = min(difference, len(ordered))
                daily_counts[ordered[:adjustment]] += 1
                difference -= adjustment
            else:
                candidates = np.flatnonzero(daily_counts > 0)
                priorities = daily_counts[candidates] - raw_counts[candidates]
                ordered = candidates[np.argsort(priorities)[::-1]]
                adjustment = min(-difference, len(ordered))
                daily_counts[ordered[:adjustment]] -= 1
                difference += adjustment

        frames.append(
            pd.DataFrame(
                {
                    "date": dates,
                    "monthly_mean_census": monthly_mean,
                    "occupied_beds": daily_counts,
                    "occupancy_rate": daily_counts / capacity,
                }
            )
        )

    return pd.concat(frames, ignore_index=True)
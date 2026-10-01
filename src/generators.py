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
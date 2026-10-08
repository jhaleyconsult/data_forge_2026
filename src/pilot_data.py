"""Generate reproducible patient and room inputs for the one-hall pilot."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


def _lognormal_parameters(mean: float, coefficient_of_variation: float) -> tuple[float, float]:
    """Return mu and sigma for a log-normal distribution with the requested mean and CV."""
    if mean <= 0:
        raise ValueError("LOS means must be positive")
    if coefficient_of_variation < 0:
        raise ValueError("LOS coefficient of variation must be non-negative")

    sigma_squared = np.log1p(coefficient_of_variation**2)
    return float(np.log(mean) - sigma_squared / 2), float(np.sqrt(sigma_squared))


def _category_los_means(daily_record: pd.Series, overall_los: float) -> dict[str, float]:
    """Read daily category LOS means, using the documented overall mean for ICU."""
    means: dict[str, float] = {}
    for column, value in daily_record.items():
        if not column.startswith("avg_los_") or not column.endswith("_days"):
            continue
        if pd.isna(value):
            continue
        category = column.removeprefix("avg_los_").removesuffix("_days")
        means[category] = float(value)
    means["intensive"] = overall_los
    return means


def generate_pilot_inputs(
    appointments: pd.DataFrame,
    daily_records: pd.Series | pd.DataFrame,
    pilot_config: Mapping[str, Any],
    room_need_config: Mapping[str, Any],
    seeds: Mapping[str, int],
    overall_los_mean: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate starting-room conditions and scaled patient arrivals.

    ``appointments`` may cover the full simulation horizon. The returned room
    table has one row per pilot room; arrivals include elapsed minutes from the
    simulation start and a sampled total length of stay.
    """
    required_appointment_columns = {
        "appointment_id",
        "source_key",
        "date",
        "category",
        "check_in_time",
    }
    missing_columns = required_appointment_columns - set(appointments.columns)
    if missing_columns:
        raise KeyError(f"appointments are missing columns: {sorted(missing_columns)}")
    if appointments.empty:
        raise ValueError("appointments must contain records for the pilot horizon")

    room_count = int(pilot_config["modeled_room_count"])
    date = str(pilot_config["date"])
    daily_frame = (
        daily_records.to_frame().T
        if isinstance(daily_records, pd.Series)
        else daily_records.copy()
    )
    daily_frame["date"] = daily_frame["date"].astype(str)
    if daily_frame["date"].duplicated().any():
        raise ValueError("daily census must contain at most one record per date")
    daily_by_date = {
        str(row["date"]): row
        for _, row in daily_frame.iterrows()
    }
    if room_count <= 0:
        raise ValueError("modeled_room_count must be positive")
    if date not in daily_by_date:
        raise ValueError(f"daily census has no record for pilot start date {date}")
    appointments = appointments.copy()
    appointments["date"] = appointments["date"].astype(str)
    appointment_dates = set(appointments["date"])
    missing_dates = sorted(appointment_dates - set(daily_by_date))
    if missing_dates:
        raise ValueError(f"daily census has no records for appointment dates: {missing_dates}")
    start_date = pd.Timestamp(date)
    horizon_hours = float(pilot_config["simulation_horizon_hours"])
    if horizon_hours <= 0:
        raise ValueError("simulation_horizon_hours must be positive")
    horizon_end = start_date + pd.Timedelta(hours=horizon_hours)
    appointment_datetimes = pd.to_datetime(
        appointments["date"] + " " + appointments["check_in_time"]
    )
    if (appointment_datetimes < start_date).any():
        raise ValueError("appointments cannot precede the configured pilot start date")
    if (appointment_datetimes >= horizon_end).any():
        raise ValueError("appointments cannot fall outside the simulation horizon")
    daily_record = daily_by_date[date]

    staffed_beds = float(daily_record["total_staffed_beds"])
    occupied_beds = float(daily_record["total_occupied_beds"])
    arrival_probability = float(pilot_config["arrival_sampling_probability"])
    if staffed_beds <= 0 or not 0 <= occupied_beds <= staffed_beds:
        raise ValueError("daily occupied and staffed bed counts are invalid")
    if not 0 <= arrival_probability <= 1:
        raise ValueError("arrival_sampling_probability must be between zero and one")

    occupied_room_count = int(
        np.floor(occupied_beds / staffed_beds * room_count + 0.5)
    )
    if occupied_room_count > room_count:
        raise ValueError("initial occupied room count exceeds pilot room count")

    cv = float(pilot_config["patient_length_of_stay"]["coefficient_of_variation"])
    minimum_los = float(pilot_config["patient_length_of_stay"]["minimum_days"])
    dirty_probability = float(
        room_need_config["probability_unoccupied_room_needs_cleaning"]
    )
    if not 0 <= dirty_probability <= 1:
        raise ValueError("dirty-room probability must be between zero and one")
    if pilot_config["patient_length_of_stay"]["distribution"] != "lognormal":
        raise ValueError("pilot patient stays require a lognormal distribution")

    category_occupancy: dict[str, float] = {}
    for column, value in daily_record.items():
        if not column.startswith("occupied_beds_"):
            continue
        if pd.isna(value):
            continue
        category = column.removeprefix("occupied_beds_")
        if float(value) > 0:
            category_occupancy[category] = float(value)
    if not category_occupancy:
        raise ValueError("daily record has no usable category occupancy")

    categories = np.array(list(category_occupancy), dtype=object)
    category_weights = np.array(list(category_occupancy.values()), dtype=float)
    category_weights /= category_weights.sum()
    los_means_by_date = {
        record_date: _category_los_means(record, overall_los_mean)
        for record_date, record in daily_by_date.items()
    }
    initial_los_means = los_means_by_date[date]
    missing_initial_means = sorted(set(category_occupancy) - set(initial_los_means))
    if missing_initial_means:
        raise ValueError(f"missing LOS means for occupied categories: {missing_initial_means}")

    room_rng = np.random.default_rng(int(seeds["room_occupancy"]))
    category_rng = np.random.default_rng(int(seeds["initial_patient_categories"]))
    residual_los_rng = np.random.default_rng(
        int(seeds["initial_patient_remaining_los"])
    )
    dirty_rng = np.random.default_rng(int(seeds["initial_room_dirty_state"]))
    arrival_rng = np.random.default_rng(int(seeds["arrival_sampling"]))
    arrival_los_rng = np.random.default_rng(int(seeds["arrival_patient_los"]))

    room_ids = [f"ROOM-{index:02d}" for index in range(1, room_count + 1)]
    occupied_room_indexes = set(
        room_rng.choice(room_count, size=occupied_room_count, replace=False).tolist()
    )
    selected_categories = category_rng.choice(
        categories, size=occupied_room_count, p=category_weights
    )

    room_rows: list[dict[str, Any]] = []
    patient_index = 0
    for index, room_id in enumerate(room_ids):
        if index not in occupied_room_indexes:
            is_dirty = bool(dirty_rng.random() < dirty_probability)
            room_rows.append({
                "date": date,
                "room_id": room_id,
                "room_state": "needs_cleaning" if is_dirty else "available",
                "occupied": False,
                "patient_id": "",
                "care_category": "",
                "total_los_days": np.nan,
                "elapsed_los_days": np.nan,
                "remaining_los_days": np.nan,
                "dirty_state": is_dirty,
            })
            continue

        category = str(selected_categories[patient_index])
        mean_los = initial_los_means[category]
        mu, sigma = _lognormal_parameters(mean_los, cv)

        # ASSUMPTION: a patient observed mid-stay is length-biased, then the
        # elapsed fraction is uniform; this gives a stationary residual-stay sample.
        total_los = float(residual_los_rng.lognormal(mu + sigma**2, sigma))
        elapsed_los = float(residual_los_rng.random() * total_los)
        remaining_los = total_los - elapsed_los
        room_rows.append({
            "date": date,
            "room_id": room_id,
            "room_state": "occupied",
            "occupied": True,
            "patient_id": f"INITIAL-{patient_index + 1:02d}",
            "care_category": category,
            "total_los_days": total_los,
            "elapsed_los_days": elapsed_los,
            "remaining_los_days": remaining_los,
            "dirty_state": pd.NA,
        })
        patient_index += 1

    # ASSUMPTION: the hall gets a proportional sample of hospital-wide arrivals;
    # appointment categories are care categories, not diagnoses or hall-specific data.
    arrival_sort_keys = list(pilot_config["arrival_sort_keys"])
    missing_sort_keys = set(arrival_sort_keys) - set(appointments.columns)
    if missing_sort_keys:
        raise KeyError(f"appointments are missing sort keys: {sorted(missing_sort_keys)}")
    ordered_appointments = appointments.sort_values(arrival_sort_keys, kind="stable")
    selected_mask = arrival_rng.random(len(ordered_appointments)) < arrival_probability
    selected = ordered_appointments.loc[selected_mask]
    arrival_rows: list[dict[str, Any]] = []
    for row in selected.itertuples(index=False):
        category = str(row.category)
        arrival_date = str(row.date)
        los_means = los_means_by_date[arrival_date]
        if category not in los_means:
            raise ValueError(
                f"no observed LOS mean for selected arrival category {category!r} on {arrival_date}"
            )
        mean_los = los_means[category]
        mu, sigma = _lognormal_parameters(mean_los, cv)
        los_days = max(float(arrival_los_rng.lognormal(mu, sigma)), minimum_los)
        arrival_datetime = pd.Timestamp(
            f"{arrival_date} {row.check_in_time}"
        )
        arrival_rows.append({
            "date": arrival_date,
            "patient_id": str(row.appointment_id),
            "source_key": str(row.source_key),
            "arrival_time": str(row.check_in_time),
            "arrival_time_minutes": (
                arrival_datetime - start_date
            ).total_seconds() / 60,
            "care_category": category,
            "total_los_days": los_days,
        })

    rooms = pd.DataFrame(room_rows)
    arrivals = pd.DataFrame(
        arrival_rows,
        columns=[
            "date",
            "patient_id",
            "source_key",
            "arrival_time",
            "arrival_time_minutes",
            "care_category",
            "total_los_days",
        ],
    )
    return rooms, arrivals


def generate_pilot_files(
    seeds: Mapping[str, int],
    overall_los_mean: float,
    root: Path | None = None,
) -> tuple[Path, Path]:
    """Load configured source data, generate pilot CSVs, and return their paths."""
    project_root = root or Path(__file__).resolve().parents[1]
    config = yaml.safe_load((project_root / "data/assumptions.yaml").read_text())
    pilot = config["simulation_pilot"]
    appointments = pd.read_csv(
        project_root / pilot["patient_arrival_source"],
        dtype={"appointment_id": str, "source_key": str, "date": str},
    )

    daily = pd.read_csv(
        project_root / pilot["initial_occupancy_source"], dtype={"date": str}
    )
    start_date = pd.Timestamp(pilot["date"])
    horizon_end = start_date + pd.Timedelta(
        hours=float(pilot["simulation_horizon_hours"])
    )
    daily_dates = pd.to_datetime(daily["date"])
    appointments = appointments.loc[
        (pd.to_datetime(appointments["date"]) >= start_date)
        & (pd.to_datetime(appointments["date"]) < horizon_end)
    ].copy()
    daily = daily.loc[
        (daily_dates >= start_date)
        & (daily_dates < horizon_end)
    ].copy()
    expected_dates = pd.date_range(
        start_date,
        periods=int(np.ceil(float(pilot["simulation_horizon_hours"]) / 24)),
        freq="D",
    )
    missing_daily_dates = sorted(set(expected_dates.strftime("%Y-%m-%d")) - set(daily["date"]))
    if missing_daily_dates:
        raise ValueError(f"daily census is missing simulation dates: {missing_daily_dates}")

    room_need = config["evs_staffing"]["baseline_rounds"]["room_need_sampling"]
    rooms, arrivals = generate_pilot_inputs(
        appointments,
        daily,
        pilot,
        room_need,
        seeds,
        overall_los_mean,
    )
    date_label = str(pilot["date"])
    outputs = (
        project_root / f"data/pilot_initial_rooms_{date_label}.csv",
        project_root / f"data/pilot_arrivals_{date_label}.csv",
    )
    rooms.to_csv(outputs[0], index=False)
    arrivals.to_csv(outputs[1], index=False)
    return outputs


if __name__ == "__main__":
    project_root = Path(__file__).resolve().parents[1]
    config = yaml.safe_load((project_root / "data/assumptions.yaml").read_text())
    generated_paths = generate_pilot_files(
        config["simulation_pilot"]["seeds"],
        config["bed_type_estimation"]["patient_flow"]["derived_average_los_days"],
        project_root,
    )
    for generated_path in generated_paths:
        print(f"Generated {generated_path}")

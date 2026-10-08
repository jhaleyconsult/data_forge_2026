"""Run the seeded, single-hall baseline simulation with SimPy."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Generator

import numpy as np
import pandas as pd
import simpy
import yaml

from src.events import (
    Patient,
    Room,
    check_in,
    check_out,
    current_care,
    finish_cleaning,
    start_cleaning,
)
from src.pilot_data import generate_pilot_files


@dataclass(frozen=True)
class SimulationResult:
    """In-memory output of one seeded pilot simulation run."""

    event_log: pd.DataFrame
    cleaner_activity: pd.DataFrame
    metrics: dict[str, float | int]


def _cleaning_unit(
    category: str | None,
    category_to_unit: dict[str, str],
    default_unit: str,
) -> str:
    """Map patient care categories to the configured EVS cleaning unit."""
    if category is None:
        return default_unit
    return category_to_unit.get(category, default_unit)


def _patient_priority(category: str, config: dict[str, Any]) -> tuple[int, str]:
    """Return a stable priority key from the configured category mapping."""
    priority_config = config["patient_queue_priority"]
    if category in priority_config["emergency_categories"]:
        name = "emergency"
    elif category in priority_config["elective_categories"]:
        name = "elective"
    else:
        name = "other"
    return priority_config["order"].index(name), name


def _ordered_room_ids(room_ids: list[str], order: str) -> list[str]:
    """Return room IDs in the configured deterministic order."""
    if order != "room_id_ascending":
        raise ValueError(f"unsupported room ordering: {order}")
    return sorted(room_ids)


def run_pilot_simulation(root: Path | None = None) -> SimulationResult:
    """Run the configured pilot horizon and return event logs and metrics."""
    project_root = root or Path(__file__).resolve().parents[1]
    config = yaml.safe_load((project_root / "data/assumptions.yaml").read_text())
    pilot = config["simulation_pilot"]
    if pilot["simulation_engine"] != "simpy":
        raise ValueError("this simulation runner requires simulation_engine: simpy")
    overall_los = float(
        config["bed_type_estimation"]["patient_flow"]["derived_average_los_days"]
    )
    generated_paths = generate_pilot_files(pilot["seeds"], overall_los, project_root)
    room_frame = pd.read_csv(generated_paths[0])
    arrival_frame = pd.read_csv(generated_paths[1])
    if room_frame.empty:
        raise ValueError("pilot room input file has no rooms")

    horizon_minutes = float(pilot["simulation_horizon_hours"]) * 60
    date = pd.Timestamp(pilot["date"])
    event_log: list[dict[str, Any]] = []
    activity_log: list[dict[str, Any]] = []
    waiting_times: dict[str, list[float]] = {
        "emergency": [],
        "elective": [],
    }
    admitted_by_priority = {"emergency": 0, "elective": 0}
    counters = {
        "arrivals": int(len(arrival_frame)),
        "admissions": 0,
        "discharges": 0,
        "completed_cleans": 0,
        "unnecessary_checks": 0,
    }
    ghost_minutes_completed = 0.0
    idle_minutes_completed = 0.0
    cleaner_work_minutes = 0.0
    cleaner_overtime_minutes = 0.0
    cleaning_started_at: dict[str, float] = {}
    waiting_requests: list[tuple[int, int, Patient, float, str]] = []
    request_sequence = 0

    rooms = {
        str(row.room_id): Room(
            room_id=str(row.room_id),
            state=str(row.room_state),
            patient=(
                Patient(
                    patient_id=str(row.patient_id),
                    care_category=str(row.care_category),
                    priority="other",
                    length_of_stay_minutes=float(row.remaining_los_days) * 1440,
                )
                if bool(row.occupied)
                else None
            ),
            cleaning_category=(
                str(row.care_category) if bool(row.occupied) else None
            ),
            last_patient_id=str(row.patient_id) if bool(row.occupied) else "",
            needs_cleaning_since=0.0 if row.room_state == "needs_cleaning" else None,
        )
        for row in room_frame.itertuples(index=False)
    }
    if any(
        room.state not in {"available", "occupied", "needs_cleaning"}
        for room in rooms.values()
    ):
        raise ValueError("pilot room input contains an unsupported initial room state")

    for room in rooms.values():
        event_log.append({
            "time_minutes": 0.0,
            "room_id": room.room_id,
            "patient_id": room.last_patient_id,
            "from_state": "",
            "to_state": room.state,
            "trigger": "initial_state",
        })

    env = simpy.Environment()
    cleaning_rng = np.random.default_rng(
        int(pilot["seeds"]["cleaning_durations"])
    )
    clean_config = config["room_cleaning"]
    cleaning_cv = float(clean_config["sampling"]["coefficient_of_variation"])
    if cleaning_cv < 0:
        raise ValueError("cleaning-time coefficient of variation must be non-negative")
    if clean_config["sampling"]["distribution"] != "lognormal":
        raise ValueError("pilot cleaner durations require a lognormal distribution")
    cleaning_sigma_squared = np.log1p(cleaning_cv**2)
    cleaning_sigma = float(np.sqrt(cleaning_sigma_squared))
    default_cleaning_unit = str(pilot["default_cleaning_unit_for_unassigned_room"])
    category_to_cleaning_unit = config["nurse_staffing"]["category_to_unit"]
    check_minutes = float(
        config["evs_staffing"]["cleaner_assignment"][
            "unnecessary_check_duration_minutes"
        ]
    )
    round_interval = float(
        config["evs_staffing"]["baseline_rounds"]["round_interval_minutes"]
    )
    cleaner_shift = pilot["cleaner_shift"]
    shift_end = (
        float(cleaner_shift["start_hour"]) + float(cleaner_shift["hours"])
    ) * 60
    productive_start = float(cleaner_shift["productive_start_hour"]) * 60
    discharge_delay = float(pilot["discharge_processing_delay_minutes"])
    room_assignment_order = str(pilot["room_assignment_order"])
    room_visit_order = str(
        config["evs_staffing"]["baseline_rounds"]["room_visit_order"]
    )
    if pilot["patient_queue_priority"]["tie_breaker"] != "arrival_order":
        raise ValueError("the pilot supports FIFO ordering within patient priority")
    if not pilot["length_of_stay_starts_at_admission"]:
        raise ValueError("pilot patient stays must start when the bed is assigned")

    def dispatch_waiting_patients() -> None:
        available_rooms = _ordered_room_ids(
            [
                room.room_id
                for room in rooms.values()
                if room.state == "available" and not room.reserved_for_check
            ],
            room_assignment_order,
        )
        while available_rooms and waiting_requests:
            waiting_requests.sort(key=lambda item: (item[0], item[1]))
            _, _, patient, queued_at, priority_name = waiting_requests.pop(0)
            room = rooms[available_rooms.pop(0)]
            patient.priority = priority_name
            check_in(room, patient, float(env.now), event_log)
            counters["admissions"] += 1
            if priority_name in waiting_times:
                waiting_times[priority_name].append(float(env.now) - queued_at)
                admitted_by_priority[priority_name] += 1
            env.process(patient_stay(room, patient))

    def admit_or_queue(patient: Patient, priority_name: str) -> None:
        nonlocal request_sequence
        available_rooms = _ordered_room_ids(
            [
                room.room_id
                for room in rooms.values()
                if room.state == "available" and not room.reserved_for_check
            ],
            room_assignment_order,
        )
        if available_rooms and not waiting_requests:
            room = rooms[available_rooms[0]]
            patient.priority = priority_name
            check_in(room, patient, float(env.now), event_log)
            counters["admissions"] += 1
            if priority_name in waiting_times:
                waiting_times[priority_name].append(0.0)
                admitted_by_priority[priority_name] += 1
            env.process(patient_stay(room, patient))
            return
        priority_order, _ = _patient_priority(patient.care_category, pilot)
        waiting_requests.append(
            (priority_order, request_sequence, patient, float(env.now), priority_name)
        )
        request_sequence += 1

    def patient_stay(
        room: Room, patient: Patient
    ) -> Generator[Any, None, None]:
        yield env.timeout(patient.length_of_stay_minutes)
        if discharge_delay:
            yield env.timeout(discharge_delay)
        if room.patient is None or room.patient.patient_id != patient.patient_id:
            raise RuntimeError(f"patient-room assignment changed unexpectedly in {room.room_id}")
        current_care(room, float(env.now), event_log)
        check_out(room, float(env.now), event_log)
        counters["discharges"] += 1

    def arrive(
        arrival_minutes: float,
        patient_id: str,
        care_category: str,
        total_los_days: float,
    ) -> Generator[Any, None, None]:
        yield env.timeout(arrival_minutes)
        _, priority_name = _patient_priority(care_category, pilot)
        patient = Patient(
            patient_id=patient_id,
            care_category=care_category,
            priority=priority_name,
            length_of_stay_minutes=total_los_days * 1440,
        )
        admit_or_queue(patient, priority_name)

    def initial_patient_discharge(room: Room) -> Generator[Any, None, None]:
        patient = room.patient
        if patient is None:
            raise RuntimeError(f"occupied input room {room.room_id} has no patient")
        yield env.timeout(patient.length_of_stay_minutes)
        if discharge_delay:
            yield env.timeout(discharge_delay)
        if room.patient is None or room.patient.patient_id != patient.patient_id:
            raise RuntimeError(f"initial patient changed unexpectedly in {room.room_id}")
        current_care(room, float(env.now), event_log)
        check_out(room, float(env.now), event_log)
        counters["discharges"] += 1

    for room in rooms.values():
        if room.state == "occupied":
            env.process(initial_patient_discharge(room))

    for row in arrival_frame.itertuples(index=False):
        env.process(
            arrive(
                float(row.arrival_time_minutes),
                str(row.patient_id),
                str(row.care_category),
                float(row.total_los_days),
            )
        )

    def cleaner_rounds() -> Generator[Any, None, None]:
        nonlocal ghost_minutes_completed
        nonlocal idle_minutes_completed
        nonlocal cleaner_work_minutes
        nonlocal cleaner_overtime_minutes
        room_order = _ordered_room_ids(list(rooms), room_visit_order)
        day_start = 0.0
        while day_start < horizon_minutes:
            day_productive_start = day_start + productive_start
            day_productive_end = day_productive_start + (
                float(cleaner_shift["productive_hours"]) * 60
            )
            day_shift_end = day_start + shift_end
            if float(env.now) < day_productive_start:
                yield env.timeout(day_productive_start - float(env.now))
            next_round_start = day_productive_start
            while (
                float(env.now) < day_productive_end
                and float(env.now) < horizon_minutes
            ):
                if float(env.now) < next_round_start:
                    yield env.timeout(next_round_start - float(env.now))
                if (
                    float(env.now) >= day_productive_end
                    or float(env.now) >= horizon_minutes
                ):
                    break
                for room_id in room_order:
                    if (
                        float(env.now) >= day_productive_end
                        or float(env.now) >= horizon_minutes
                    ):
                        break
                    room = rooms[room_id]
                    if room.state == "needs_cleaning":
                        cleaning_unit = _cleaning_unit(
                            room.cleaning_category,
                            category_to_cleaning_unit,
                            default_cleaning_unit,
                        )
                        if cleaning_unit not in clean_config["unit_minutes"]:
                            raise KeyError(f"no cleaning duration configured for {cleaning_unit}")
                        mean_clean_minutes = float(
                            clean_config["unit_minutes"][cleaning_unit]["discharge"]
                        )
                        if mean_clean_minutes <= 0:
                            raise ValueError(
                                f"cleaning duration for {cleaning_unit} must be positive"
                            )
                        mu = float(
                            np.log(mean_clean_minutes) - cleaning_sigma_squared / 2
                        )
                        duration = float(cleaning_rng.lognormal(mu, cleaning_sigma))
                        started_at = float(env.now)
                        ghost_start = room.needs_cleaning_since
                        start_cleaning(room, started_at, event_log)
                        if ghost_start is not None:
                            ghost_wait = started_at - ghost_start
                            ghost_minutes_completed += ghost_wait
                            idle_minutes_completed += ghost_wait
                        cleaning_started_at[room.room_id] = started_at
                        finishes_after_shift = started_at + duration > day_shift_end
                        if (
                            finishes_after_shift
                            and not cleaner_shift["finish_active_clean_after_shift"]
                        ):
                            duration = max(0.0, day_shift_end - started_at)
                        activity_log.append({
                            "activity": "discharge_clean",
                            "room_id": room.room_id,
                            "start_minutes": started_at,
                            "duration_minutes": duration,
                        })
                        cleaner_work_minutes += min(
                            duration, max(0.0, horizon_minutes - started_at)
                        )
                        yield env.timeout(duration)
                        finished_at = float(env.now)
                        idle_minutes_completed += finished_at - started_at
                        if (
                            finishes_after_shift
                            and not cleaner_shift["finish_active_clean_after_shift"]
                        ):
                            cleaning_started_at[room.room_id] = day_shift_end
                            break
                        cleaning_started_at.pop(room.room_id, None)
                        if finished_at > day_shift_end:
                            cleaner_overtime_minutes += max(
                                0.0, finished_at - max(started_at, day_shift_end)
                            )
                        finish_cleaning(room, finished_at, event_log)
                        counters["completed_cleans"] += 1
                        dispatch_waiting_patients()
                    elif room.state == "available":
                        if float(env.now) + check_minutes > day_productive_end:
                            break
                        room.reserved_for_check = True
                        check_started_at = float(env.now)
                        yield env.timeout(check_minutes)
                        room.reserved_for_check = False
                        cleaner_work_minutes += check_minutes
                        counters["unnecessary_checks"] += 1
                        activity_log.append({
                            "activity": "unnecessary_room_check",
                            "room_id": room.room_id,
                            "start_minutes": check_started_at,
                            "duration_minutes": check_minutes,
                        })
                        dispatch_waiting_patients()
                next_round_start += round_interval
            day_start += 1440

    env.process(cleaner_rounds())
    env.run(until=horizon_minutes)

    for room in rooms.values():
        if room.state == "needs_cleaning" and room.needs_cleaning_since is not None:
            elapsed = max(0.0, horizon_minutes - room.needs_cleaning_since)
            ghost_minutes_completed += elapsed
            idle_minutes_completed += elapsed
        elif room.state == "cleaning":
            started_at = cleaning_started_at.get(room.room_id)
            if started_at is not None:
                idle_minutes_completed += max(0.0, horizon_minutes - started_at)

    event_frame = pd.DataFrame(event_log)
    event_frame["event_datetime"] = date + pd.to_timedelta(
        event_frame["time_minutes"], unit="m"
    )
    activity_frame = pd.DataFrame(activity_log)
    if not activity_frame.empty:
        activity_frame["start_datetime"] = date + pd.to_timedelta(
            activity_frame["start_minutes"], unit="m"
        )
    productive_minutes = sum(
        max(
            0.0,
            min(
                horizon_minutes,
                day_start
                + productive_start
                + float(cleaner_shift["productive_hours"]) * 60,
            )
            - (day_start + productive_start),
        )
        for day_start in range(0, int(np.ceil(horizon_minutes)), 1440)
    )
    metrics: dict[str, float | int] = {
        "simulation_horizon_hours": horizon_minutes / 60,
        "initial_rooms": len(rooms),
        "initial_occupied_rooms": int(room_frame["occupied"].sum()),
        "initial_dirty_unoccupied_rooms": int(
            (room_frame["room_state"] == "needs_cleaning").sum()
        ),
        "scaled_arrivals": counters["arrivals"],
        "admissions": counters["admissions"],
        "discharges": counters["discharges"],
        "patients_still_waiting_at_horizon": len(waiting_requests),
        "completed_room_cleans": counters["completed_cleans"],
        "ghost_room_minutes": ghost_minutes_completed,
        "idle_bed_hours": idle_minutes_completed / 60,
        "mean_emergency_bed_wait_minutes": (
            float(np.mean(waiting_times["emergency"]))
            if waiting_times["emergency"]
            else 0.0
        ),
        "mean_elective_bed_wait_minutes": (
            float(np.mean(waiting_times["elective"]))
            if waiting_times["elective"]
            else 0.0
        ),
        "emergency_patients_admitted": admitted_by_priority["emergency"],
        "elective_patients_admitted": admitted_by_priority["elective"],
        "unnecessary_room_checks": counters["unnecessary_checks"],
        "cleaner_check_and_clean_minutes": cleaner_work_minutes,
        "cleaner_utilization_of_productive_hours": cleaner_work_minutes
        / productive_minutes
        if productive_minutes > 0
        else 0.0,
        "cleaner_overtime_minutes": cleaner_overtime_minutes,
        "rooms_awaiting_cleaning_at_horizon": sum(
            room.state == "needs_cleaning" for room in rooms.values()
        ),
        "rooms_being_cleaned_at_horizon": sum(
            room.state == "cleaning" for room in rooms.values()
        ),
    }
    return SimulationResult(event_frame, activity_frame, metrics)


if __name__ == "__main__":
    result = run_pilot_simulation()
    first_day = result.event_log["event_datetime"].min().date()
    print(
        f"Pilot baseline from {first_day} "
        f"({result.metrics['simulation_horizon_hours']} hours)"
    )
    for metric, value in result.metrics.items():
        print(f"{metric}: {value}")

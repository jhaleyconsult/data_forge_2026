"""Framework-independent room and patient state transitions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


BED_STATES = (
    "available",
    "occupied",
    "discharge_pending",
    "needs_cleaning",
    "cleaning",
)
_ALLOWED_TRANSITIONS = {
    "available": "occupied",
    "occupied": "discharge_pending",
    "discharge_pending": "needs_cleaning",
    "needs_cleaning": "cleaning",
    "cleaning": "available",
}


@dataclass
class Patient:
    """A synthetic inpatient and the time they need a bed."""

    patient_id: str
    care_category: str
    priority: str
    length_of_stay_minutes: float


@dataclass
class Room:
    """A pilot room with its current bed state and patient."""

    room_id: str
    state: str
    patient: Patient | None = None
    cleaning_category: str | None = None
    last_patient_id: str = ""
    needs_cleaning_since: float | None = None
    reserved_for_check: bool = False


def _record_transition(
    room: Room,
    next_state: str,
    time_minutes: float,
    event_log: list[dict[str, Any]],
    trigger: str,
) -> None:
    if next_state not in BED_STATES:
        raise ValueError(f"unknown bed state: {next_state}")
    if _ALLOWED_TRANSITIONS.get(room.state) != next_state:
        raise ValueError(
            f"invalid room transition: {room.state} -> {next_state}"
        )
    event_log.append({
        "time_minutes": time_minutes,
        "room_id": room.room_id,
        "patient_id": (
            room.patient.patient_id if room.patient else room.last_patient_id
        ),
        "from_state": room.state,
        "to_state": next_state,
        "trigger": trigger,
    })
    room.state = next_state
    if next_state == "needs_cleaning":
        room.needs_cleaning_since = time_minutes
    elif next_state == "available":
        room.needs_cleaning_since = None


def check_in(
    room: Room,
    patient: Patient,
    time_minutes: float,
    event_log: list[dict[str, Any]],
) -> None:
    """Assign a patient to an available room."""
    if room.state != "available" or room.reserved_for_check:
        raise ValueError(f"room {room.room_id} is not available for check-in")
    room.patient = patient
    room.last_patient_id = patient.patient_id
    _record_transition(room, "occupied", time_minutes, event_log, "check_in")


def current_care(
    room: Room,
    time_minutes: float,
    event_log: list[dict[str, Any]],
) -> None:
    """Mark the occupied patient's care complete and ready for discharge."""
    if room.state != "occupied" or room.patient is None:
        raise ValueError(f"room {room.room_id} has no occupied patient to discharge")
    _record_transition(room, "discharge_pending", time_minutes, event_log, "current_care")


def check_out(
    room: Room,
    time_minutes: float,
    event_log: list[dict[str, Any]],
) -> Patient:
    """Remove a ready-to-leave patient and mark the room as needing cleaning."""
    if room.state != "discharge_pending" or room.patient is None:
        raise ValueError(f"room {room.room_id} has no patient ready for check-out")
    patient = room.patient
    room.cleaning_category = patient.care_category
    _record_transition(room, "needs_cleaning", time_minutes, event_log, "check_out")
    room.patient = None
    return patient


def start_cleaning(
    room: Room,
    time_minutes: float,
    event_log: list[dict[str, Any]],
) -> None:
    """Start cleaning a room that is waiting for EVS."""
    if room.state != "needs_cleaning":
        raise ValueError(f"room {room.room_id} does not need cleaning")
    _record_transition(room, "cleaning", time_minutes, event_log, "cleaning_started")


def finish_cleaning(
    room: Room,
    time_minutes: float,
    event_log: list[dict[str, Any]],
) -> None:
    """Return a cleaned room to the available state."""
    if room.state != "cleaning":
        raise ValueError(f"room {room.room_id} is not being cleaned")
    _record_transition(room, "available", time_minutes, event_log, "cleaning_finished")
    room.cleaning_category = None

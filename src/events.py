"""Shared patient bed-state transitions for the API and simulation."""

from __future__ import annotations

from typing import Literal, Protocol

BedStatus = Literal[
    "available",
    "occupied",
    "discharge_pending",
    "needs_cleaning",
    "cleaning",
]
CareUpdate = Literal["ready", "needs_more_time"]


class StatusStore(Protocol):
    """Storage interface used by bed-state transition functions."""

    def get_status(self, patient_id: str) -> BedStatus | None:
        """Return a patient's current status, if one is recorded."""

    def set_status(self, patient_id: str, status: BedStatus) -> None:
        """Persist a patient's current status."""


def check_in(store: StatusStore, patient_id: str) -> BedStatus:
    """Record a patient as occupying a bed."""
    _validate_patient_id(patient_id)
    if store.get_status(patient_id) is not None:
        raise ValueError(f"Patient {patient_id!r} already has a bed status")
    store.set_status(patient_id, "occupied")
    return "occupied"


def current_care(
    store: StatusStore, patient_id: str, update: CareUpdate
) -> BedStatus:
    """Keep an occupied stay active or mark it discharge-pending when ready."""
    _validate_patient_id(patient_id)
    status = store.get_status(patient_id)
    if status is None:
        raise KeyError(patient_id)
    if update == "needs_more_time":
        if status != "occupied":
            raise ValueError("Current-care updates require an occupied bed")
        return status
    if status == "occupied":
        store.set_status(patient_id, "discharge_pending")
        return "discharge_pending"
    if status == "discharge_pending":
        return status
    raise ValueError("A patient can only be marked ready while occupying a bed")


def check_out(store: StatusStore, patient_id: str) -> BedStatus:
    """Move a discharge-pending patient's bed into the cleaning queue."""
    _validate_patient_id(patient_id)
    status = store.get_status(patient_id)
    if status is None:
        raise KeyError(patient_id)
    if status == "needs_cleaning":
        return status
    if status != "discharge_pending":
        raise ValueError("A patient must be discharge-pending before check-out")
    store.set_status(patient_id, "needs_cleaning")
    return "needs_cleaning"


def _validate_patient_id(patient_id: str) -> None:
    if not patient_id.strip():
        raise ValueError("patient_id must not be empty")
"""Read-only patient status endpoint."""

from fastapi import APIRouter, HTTPException

from src.api.schemas import StatusResponse
from src.api.state_store import state_store

router = APIRouter()


@router.get("/patients/{patient_id}/status", response_model=StatusResponse)
def get_patient_status(patient_id: str) -> StatusResponse:
    """Return the patient's current bed status without changing it."""
    status = state_store.get_status(patient_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return StatusResponse(
        message="Current patient status",
        patient_id=patient_id,
        status=status,
    )
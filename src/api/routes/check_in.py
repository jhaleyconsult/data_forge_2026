"""Patient check-in endpoint."""

from fastapi import APIRouter, HTTPException

from src.api.schemas import PatientRequest, StatusResponse
from src.api.state_store import state_store
from src.events import check_in

router = APIRouter()


@router.post("/check-in", response_model=StatusResponse)
def check_in_patient(request: PatientRequest) -> StatusResponse:
    """Record check-in and return the demo acknowledgment."""
    try:
        status = check_in(state_store, request.patient_id)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return StatusResponse(
        message="Hello World from check-in",
        patient_id=request.patient_id,
        status=status,
    )
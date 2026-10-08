"""Patient check-out endpoint."""

from fastapi import APIRouter, HTTPException

from src.api.schemas import PatientRequest, StatusResponse
from src.api.state_store import state_store
from src.events import check_out

router = APIRouter()


@router.post("/check-out", response_model=StatusResponse)
def check_out_patient(request: PatientRequest) -> StatusResponse:
    """Record check-out and return the demo acknowledgment."""
    try:
        status = check_out(state_store, request.patient_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Patient not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return StatusResponse(
        message="Hello World from check-out",
        patient_id=request.patient_id,
        status=status,
    )
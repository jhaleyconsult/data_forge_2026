"""Current-care update endpoint."""

from fastapi import APIRouter, HTTPException

from src.api.schemas import CurrentCareRequest, StatusResponse
from src.api.state_store import state_store
from src.events import current_care

router = APIRouter()


@router.put("/current-care", response_model=StatusResponse)
def update_current_care(request: CurrentCareRequest) -> StatusResponse:
    """Record a care update and return the demo acknowledgment."""
    try:
        status = current_care(state_store, request.patient_id, request.update)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Patient not found") from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return StatusResponse(
        message="Hello World from current-care",
        patient_id=request.patient_id,
        status=status,
    )
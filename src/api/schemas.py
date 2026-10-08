"""Request and response models for the bed-turnover API."""

from typing import Literal

from pydantic import BaseModel, Field

from src.events import BedStatus


class PatientRequest(BaseModel):
    """Request identifying one synthetic patient."""

    patient_id: str = Field(min_length=1)


class CurrentCareRequest(PatientRequest):
    """Nurse's current-care update for a patient."""

    update: Literal["ready", "needs_more_time"]


class StatusResponse(BaseModel):
    """Patient status returned by a workflow route or status lookup."""

    message: str
    patient_id: str
    status: BedStatus
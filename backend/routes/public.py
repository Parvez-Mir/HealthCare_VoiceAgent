"""Unauthenticated runtime routes used by the voice worker."""

from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.runtime_state import (
    BOOKED_SLOTS,
    BOOKING_LOCK,
    PATIENTS_PATH,
    SLOTS_PATH,
)
from services.file_store import load_json

router = APIRouter(tags=["runtime"])


class AppointmentRequest(BaseModel):
    patient_id: str = Field(min_length=1)
    slot_id: str = Field(min_length=1)


class AppointmentResponse(BaseModel):
    confirmation_id: str
    patient_id: str
    slot_id: str
    provider: str
    starts_at: str
    duration_minutes: int
    status: str


@router.get("/slots")
def list_available_slots() -> list[dict]:
    """Return consultation slots that have not been booked."""
    slots = load_json(SLOTS_PATH)
    with BOOKING_LOCK:
        return [slot for slot in slots if slot["id"] not in BOOKED_SLOTS]


@router.post("/appointments", response_model=AppointmentResponse, status_code=201)
def create_appointment(request: AppointmentRequest) -> AppointmentResponse:
    """Book one available consultation slot for a known patient."""
    patients = load_json(PATIENTS_PATH)
    slots = load_json(SLOTS_PATH)
    if request.patient_id not in {patient["id"] for patient in patients}:
        raise HTTPException(status_code=404, detail="Patient not found")

    slot = next((item for item in slots if item["id"] == request.slot_id), None)
    if slot is None:
        raise HTTPException(status_code=404, detail="Appointment slot not found")

    with BOOKING_LOCK:
        if request.slot_id in BOOKED_SLOTS:
            raise HTTPException(status_code=409, detail="Appointment slot is no longer available")
        BOOKED_SLOTS.add(request.slot_id)

    return AppointmentResponse(
        confirmation_id=f"confirm-{uuid4().hex[:12]}",
        patient_id=request.patient_id,
        slot_id=request.slot_id,
        provider=slot["provider"],
        starts_at=slot["starts_at"],
        duration_minutes=slot["duration_minutes"],
        status="booked",
    )


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

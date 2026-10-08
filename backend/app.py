import json
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field


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


PATIENTS_PATH = Path(__file__).with_name("patients.json")
with PATIENTS_PATH.open(encoding="utf-8") as patients_file:
    PATIENTS = json.load(patients_file)

SLOTS_PATH = Path(__file__).with_name("slots.json")
with SLOTS_PATH.open(encoding="utf-8") as slots_file:
    SLOTS = json.load(slots_file)

SLOT_IDS = {slot["id"] for slot in SLOTS}
BOOKED_SLOTS: set[str] = set()
BOOKING_LOCK = Lock()

app = FastAPI(title="Healthcare Voice Agent Backend", version="0.1.0")


@app.get("/slots")
def get_slots() -> list[dict]:
    """Return the currently available fake consultation slots."""
    with BOOKING_LOCK:
        return [slot for slot in SLOTS if slot["id"] not in BOOKED_SLOTS]


@app.post("/appointments", response_model=AppointmentResponse, status_code=201)
def book_appointment(request: AppointmentRequest) -> AppointmentResponse:
    """Book one fake consultation slot for a known dummy patient."""
    patient_ids = {patient["id"] for patient in PATIENTS}
    if request.patient_id not in patient_ids:
        raise HTTPException(status_code=404, detail="Patient not found")

    if request.slot_id not in SLOT_IDS:
        raise HTTPException(status_code=404, detail="Appointment slot not found")

    with BOOKING_LOCK:
        if request.slot_id in BOOKED_SLOTS:
            raise HTTPException(status_code=409, detail="Appointment slot is no longer available")
        BOOKED_SLOTS.add(request.slot_id)

    slot = next(slot for slot in SLOTS if slot["id"] == request.slot_id)
    return AppointmentResponse(
        confirmation_id=f"confirm-{uuid4().hex[:12]}",
        patient_id=request.patient_id,
        slot_id=request.slot_id,
        provider=slot["provider"],
        starts_at=slot["starts_at"],
        duration_minutes=slot["duration_minutes"],
        status="booked",
    )


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

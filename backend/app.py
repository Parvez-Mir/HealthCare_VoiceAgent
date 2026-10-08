import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
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


class LoginRequest(BaseModel):
    email: str = Field(min_length=1)
    password: str = Field(min_length=1)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    user: dict[str, str]


class Biomarkers(BaseModel):
    glucose_mg_dl: float = Field(ge=0, le=1000)
    hba1c_percent: float = Field(ge=0, le=100)


class PatientRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(min_length=7, max_length=20)
    biomarkers: Biomarkers


class SlotRequest(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    provider: str = Field(min_length=2, max_length=120)
    starts_at: datetime
    duration_minutes: int = Field(ge=5, le=240)


class CallDispatchRequest(BaseModel):
    patient_id: str = Field(min_length=1)


PATIENTS_PATH = Path(__file__).with_name("patients.json")
with PATIENTS_PATH.open(encoding="utf-8") as patients_file:
    PATIENTS = json.load(patients_file)

SLOTS_PATH = Path(__file__).with_name("slots.json")
with SLOTS_PATH.open(encoding="utf-8") as slots_file:
    SLOTS = json.load(slots_file)

SLOT_IDS = {slot["id"] for slot in SLOTS}
BOOKED_SLOTS: set[str] = set()
BOOKING_LOCK = Lock()
SESSION_TOKENS: set[str] = set()
SESSION_LOCK = Lock()
PATIENTS_LOCK = Lock()
SLOTS_LOCK = Lock()
DEVELOPMENT_EMAIL = "admin@careline.dev"
DEVELOPMENT_PASSWORD = "careline-dev"
DEVELOPMENT_USER = {"email": DEVELOPMENT_EMAIL, "name": "Careline operator"}
BEARER_SCHEME = HTTPBearer(auto_error=False)

app = FastAPI(title="Healthcare Voice Agent Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def require_dashboard_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(BEARER_SCHEME),
) -> dict[str, str]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Dashboard authentication required")
    with SESSION_LOCK:
        if credentials.credentials not in SESSION_TOKENS:
            raise HTTPException(status_code=401, detail="Dashboard session is invalid or expired")
    return DEVELOPMENT_USER


@app.post("/auth/login", response_model=LoginResponse)
def login(request: LoginRequest) -> LoginResponse:
    if request.email != DEVELOPMENT_EMAIL or request.password != DEVELOPMENT_PASSWORD:
        raise HTTPException(status_code=401, detail="Invalid development account credentials")

    token = secrets.token_urlsafe(32)
    with SESSION_LOCK:
        SESSION_TOKENS.add(token)
    return LoginResponse(access_token=token, token_type="bearer", user=DEVELOPMENT_USER)


@app.post("/auth/logout", status_code=204)
def logout(credentials: HTTPAuthorizationCredentials | None = Depends(BEARER_SCHEME)) -> None:
    if credentials is not None:
        with SESSION_LOCK:
            SESSION_TOKENS.discard(credentials.credentials)


@app.get("/dashboard/summary")
def dashboard_summary(_: dict[str, str] = Depends(require_dashboard_session)) -> dict[str, int | str]:
    with BOOKING_LOCK:
        open_slot_count = sum(1 for slot in SLOTS if slot["id"] not in BOOKED_SLOTS)
    with PATIENTS_PATH.open(encoding="utf-8") as patients_file:
        patients = json.load(patients_file)
    prompts_path = Path(__file__).with_name("agent_prompts.json")
    with prompts_path.open(encoding="utf-8") as prompts_file:
        prompts = json.load(prompts_file)
    return {
        "patient_count": len(patients),
        "open_slot_count": open_slot_count,
        "prompt_count": len(prompts),
        "active_prompt_id": os.getenv("AGENT_PROMPT_ID", "flora-healthcare-agent-v1"),
    }


def load_patients() -> list[dict]:
    with PATIENTS_PATH.open(encoding="utf-8") as patients_file:
        return json.load(patients_file)


def save_patients(patients: list[dict]) -> None:
    temporary_path = PATIENTS_PATH.with_suffix(".json.tmp")
    with temporary_path.open("w", encoding="utf-8") as patients_file:
        json.dump(patients, patients_file, indent=2)
        patients_file.write("\n")
    os.replace(temporary_path, PATIENTS_PATH)


def load_slots() -> list[dict]:
    with SLOTS_PATH.open(encoding="utf-8") as slots_file:
        return json.load(slots_file)


def save_slots(slots: list[dict]) -> None:
    temporary_path = SLOTS_PATH.with_suffix(".json.tmp")
    with temporary_path.open("w", encoding="utf-8") as slots_file:
        json.dump(slots, slots_file, indent=2)
        slots_file.write("\n")
    os.replace(temporary_path, SLOTS_PATH)


def validate_phone(phone: str) -> str:
    normalized = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not re.fullmatch(r"\+[1-9]\d{6,14}", normalized):
        raise HTTPException(status_code=422, detail="Phone must use international format, for example +919876543210")
    return normalized


@app.get("/patients", response_model=list[dict])
def list_patients(_: dict[str, str] = Depends(require_dashboard_session)) -> list[dict]:
    with PATIENTS_LOCK:
        return load_patients()


@app.get("/patients/{patient_id}", response_model=dict)
def get_patient(patient_id: str, _: dict[str, str] = Depends(require_dashboard_session)) -> dict:
    with PATIENTS_LOCK:
        patient = next((item for item in load_patients() if item["id"] == patient_id), None)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient


@app.post("/patients", response_model=dict, status_code=201)
def create_patient(request: PatientRequest, _: dict[str, str] = Depends(require_dashboard_session)) -> dict:
    patient = request.model_dump()
    patient["phone"] = validate_phone(patient["phone"])
    with PATIENTS_LOCK:
        patients = load_patients()
        if any(item["id"] == patient["id"] for item in patients):
            raise HTTPException(status_code=409, detail="A patient with this ID already exists")
        patients.append(patient)
        save_patients(patients)
    PATIENTS[:] = patients
    return patient


@app.put("/patients/{patient_id}", response_model=dict)
def update_patient(
    patient_id: str,
    request: PatientRequest,
    _: dict[str, str] = Depends(require_dashboard_session),
) -> dict:
    if request.id != patient_id:
        raise HTTPException(status_code=400, detail="Patient ID cannot be changed")
    patient = request.model_dump()
    patient["phone"] = validate_phone(patient["phone"])
    with PATIENTS_LOCK:
        patients = load_patients()
        index = next((position for position, item in enumerate(patients) if item["id"] == patient_id), None)
        if index is None:
            raise HTTPException(status_code=404, detail="Patient not found")
        patients[index] = patient
        save_patients(patients)
    PATIENTS[:] = patients
    return patient


@app.delete("/patients/{patient_id}", status_code=204)
def delete_patient(patient_id: str, _: dict[str, str] = Depends(require_dashboard_session)) -> None:
    with PATIENTS_LOCK:
        patients = load_patients()
        remaining = [patient for patient in patients if patient["id"] != patient_id]
        if len(remaining) == len(patients):
            raise HTTPException(status_code=404, detail="Patient not found")
        save_patients(remaining)
    PATIENTS[:] = remaining


@app.get("/dashboard/slots", response_model=list[dict])
def list_dashboard_slots(_: dict[str, str] = Depends(require_dashboard_session)) -> list[dict]:
    with SLOTS_LOCK, BOOKING_LOCK:
        return [
            {**slot, "status": "booked" if slot["id"] in BOOKED_SLOTS else "available"}
            for slot in load_slots()
        ]


@app.post("/dashboard/slots", response_model=dict, status_code=201)
def create_dashboard_slot(
    request: SlotRequest,
    _: dict[str, str] = Depends(require_dashboard_session),
) -> dict:
    slot = request.model_dump()
    slot["starts_at"] = request.starts_at.isoformat()
    with SLOTS_LOCK:
        slots = load_slots()
        if any(item["id"] == slot["id"] for item in slots):
            raise HTTPException(status_code=409, detail="A slot with this ID already exists")
        slots.append(slot)
        save_slots(slots)
    SLOTS[:] = slots
    SLOT_IDS.clear()
    SLOT_IDS.update(slot["id"] for slot in slots)
    return {**slot, "status": "available"}


@app.put("/dashboard/slots/{slot_id}", response_model=dict)
def update_dashboard_slot(
    slot_id: str,
    request: SlotRequest,
    _: dict[str, str] = Depends(require_dashboard_session),
) -> dict:
    if request.id != slot_id:
        raise HTTPException(status_code=400, detail="Slot ID cannot be changed")
    slot = request.model_dump()
    slot["starts_at"] = request.starts_at.isoformat()
    with SLOTS_LOCK, BOOKING_LOCK:
        slots = load_slots()
        index = next((position for position, item in enumerate(slots) if item["id"] == slot_id), None)
        if index is None:
            raise HTTPException(status_code=404, detail="Appointment slot not found")
        if slot_id in BOOKED_SLOTS:
            raise HTTPException(status_code=409, detail="Booked slots cannot be edited")
        slots[index] = slot
        save_slots(slots)
    SLOTS[:] = slots
    SLOT_IDS.clear()
    SLOT_IDS.update(item["id"] for item in slots)
    return {**slot, "status": "available"}


@app.delete("/dashboard/slots/{slot_id}", status_code=204)
def delete_dashboard_slot(
    slot_id: str,
    _: dict[str, str] = Depends(require_dashboard_session),
) -> None:
    with SLOTS_LOCK, BOOKING_LOCK:
        if slot_id in BOOKED_SLOTS:
            raise HTTPException(status_code=409, detail="Booked slots cannot be deleted")
        slots = load_slots()
        remaining = [slot for slot in slots if slot["id"] != slot_id]
        if len(remaining) == len(slots):
            raise HTTPException(status_code=404, detail="Appointment slot not found")
        save_slots(remaining)
    SLOTS[:] = remaining
    SLOT_IDS.clear()
    SLOT_IDS.update(slot["id"] for slot in remaining)


@app.post("/calls", response_model=dict, status_code=202)
async def dispatch_patient_call(
    request: CallDispatchRequest,
    _: dict[str, str] = Depends(require_dashboard_session),
) -> dict[str, str]:
    with PATIENTS_LOCK:
        patient = next((item for item in load_patients() if item["id"] == request.patient_id), None)
    if patient is None:
        raise HTTPException(status_code=404, detail="Patient not found")
    phone = validate_phone(patient["phone"])
    try:
        from make_call import dispatch_call

        room_name = await dispatch_call(patient["id"], phone)
    except (RuntimeError, SystemExit) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (OSError, ValueError) as error:
        raise HTTPException(status_code=502, detail="Outbound call dispatch failed") from error
    return {"patient_id": patient["id"], "phone_number": phone, "room": room_name, "status": "dispatched"}


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

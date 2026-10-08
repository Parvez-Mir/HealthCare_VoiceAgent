import json
import os
import re
import secrets
from datetime import datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4
from urllib.parse import urlparse

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


class DeveloperConfigUpdate(BaseModel):
    values: dict[str, str]


class PromptRequest(BaseModel):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    description: str = Field(min_length=1, max_length=240)
    template: str = Field(min_length=1, max_length=12000)


class PromptPreviewRequest(BaseModel):
    template: str = Field(min_length=1, max_length=12000)


PATIENTS_PATH = Path(__file__).with_name("patients.json")
with PATIENTS_PATH.open(encoding="utf-8") as patients_file:
    PATIENTS = json.load(patients_file)

SLOTS_PATH = Path(__file__).with_name("slots.json")
with SLOTS_PATH.open(encoding="utf-8") as slots_file:
    SLOTS = json.load(slots_file)

ENV_PATH = Path(__file__).with_name(".env")
ENV_EXAMPLE_PATH = Path(__file__).with_name(".env.example")
PROMPTS_PATH = Path(__file__).with_name("agent_prompts.json")
SLOT_IDS = {slot["id"] for slot in SLOTS}
BOOKED_SLOTS: set[str] = set()
BOOKING_LOCK = Lock()
SESSION_TOKENS: set[str] = set()
SESSION_LOCK = Lock()
PATIENTS_LOCK = Lock()
SLOTS_LOCK = Lock()
ENV_LOCK = Lock()
PROMPTS_LOCK = Lock()
DEVELOPMENT_EMAIL = "admin@careline.dev"
DEVELOPMENT_PASSWORD = "careline-dev"
DEVELOPMENT_USER = {"email": DEVELOPMENT_EMAIL, "name": "Careline operator"}
BEARER_SCHEME = HTTPBearer(auto_error=False)
CONFIG_SECRET_KEYS = {
    "ASSEMBLYAI_API_KEY",
    "CARTESIA_API_KEY",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "OPIK_API_KEY",
}
CONFIG_KEYS = [
    "OLLAMA_MODEL",
    "OLLAMA_BASE_URL",
    "ASSEMBLYAI_API_KEY",
    "CARTESIA_API_KEY",
    "CARTESIA_VOICE_ID",
    "PATIENT_ID",
    "AGENT_PROMPT_ID",
    "LIVEKIT_URL",
    "LIVEKIT_API_KEY",
    "LIVEKIT_API_SECRET",
    "SIP_OUTBOUND_TRUNK_ID",
    "OPIK_API_KEY",
    "OPIK_WORKSPACE",
    "OPIK_PROJECT_NAME",
]
SUPPORTED_PROMPT_VARIABLES = {"patient_id", "patient_name", "glucose_mg_dl", "hba1c_percent"}

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


@app.get("/developer/config")
def get_developer_config(_: dict[str, str] = Depends(require_dashboard_session)) -> dict[str, list[dict[str, str | bool]]]:
    with ENV_LOCK:
        return {"settings": config_payload()}


@app.put("/developer/config")
def update_developer_config(
    request: DeveloperConfigUpdate,
    _: dict[str, str] = Depends(require_dashboard_session),
) -> dict[str, list[dict[str, str | bool]]]:
    unknown = set(request.values) - set(CONFIG_KEYS)
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unsupported settings: {', '.join(sorted(unknown))}")
    for key, value in request.values.items():
        if key.endswith("_URL") and value:
            parsed = urlparse(value)
            if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.netloc:
                raise HTTPException(status_code=422, detail=f"{key} must be a valid URL")
        if key == "AGENT_PROMPT_ID" and value:
            with PROMPTS_LOCK:
                if not any(prompt["id"] == value for prompt in load_prompts()):
                    raise HTTPException(status_code=422, detail="AGENT_PROMPT_ID must reference an existing prompt")
    current_values = read_env_values()
    updates = dict(request.values)
    for key in CONFIG_SECRET_KEYS:
        if key in updates and not updates[key]:
            updates[key] = current_values.get(key, "")
    with ENV_LOCK:
        save_env_values(updates)
    for key, value in updates.items():
        if value:
            os.environ[key] = value
        elif key in os.environ:
            os.environ.pop(key)
    return {"settings": config_payload()}


@app.post("/developer/config/test")
def test_developer_config(_: dict[str, str] = Depends(require_dashboard_session)) -> dict[str, object]:
    values = read_env_values()
    checks = {
        "ollama": bool(values.get("OLLAMA_MODEL") and values.get("OLLAMA_BASE_URL")),
        "livekit": bool(values.get("LIVEKIT_URL") and values.get("LIVEKIT_API_KEY") and values.get("LIVEKIT_API_SECRET")),
        "speech_providers": bool(values.get("ASSEMBLYAI_API_KEY") and values.get("CARTESIA_API_KEY")),
        "outbound_sip": bool(values.get("SIP_OUTBOUND_TRUNK_ID")),
        "opik": bool(values.get("OPIK_API_KEY") and values.get("OPIK_WORKSPACE")),
    }
    return {"checks": checks, "configured_count": sum(checks.values()), "total_count": len(checks)}


@app.get("/developer/prompts")
def list_developer_prompts(_: dict[str, str] = Depends(require_dashboard_session)) -> dict[str, object]:
    with PROMPTS_LOCK:
        prompts = load_prompts()
    active_prompt_id = read_env_values().get("AGENT_PROMPT_ID", "flora-healthcare-agent-v1")
    return {"prompts": [{**prompt, "active": prompt["id"] == active_prompt_id} for prompt in prompts]}


@app.post("/developer/prompts", response_model=dict, status_code=201)
def create_developer_prompt(
    request: PromptRequest,
    _: dict[str, str] = Depends(require_dashboard_session),
) -> dict:
    validate_prompt_template(request.template)
    prompt = request.model_dump()
    with PROMPTS_LOCK:
        prompts = load_prompts()
        if any(item["id"] == prompt["id"] for item in prompts):
            raise HTTPException(status_code=409, detail="A prompt with this ID already exists")
        prompts.append(prompt)
        save_prompts(prompts)
    return prompt


@app.put("/developer/prompts/{prompt_id}", response_model=dict)
def update_developer_prompt(
    prompt_id: str,
    request: PromptRequest,
    _: dict[str, str] = Depends(require_dashboard_session),
) -> dict:
    if request.id != prompt_id:
        raise HTTPException(status_code=400, detail="Prompt ID cannot be changed")
    validate_prompt_template(request.template)
    prompt = request.model_dump()
    with PROMPTS_LOCK:
        prompts = load_prompts()
        index = next((position for position, item in enumerate(prompts) if item["id"] == prompt_id), None)
        if index is None:
            raise HTTPException(status_code=404, detail="Prompt not found")
        prompts[index] = prompt
        save_prompts(prompts)
    return prompt


@app.delete("/developer/prompts/{prompt_id}", status_code=204)
def delete_developer_prompt(
    prompt_id: str,
    _: dict[str, str] = Depends(require_dashboard_session),
) -> None:
    with PROMPTS_LOCK:
        prompts = load_prompts()
        if len(prompts) <= 1:
            raise HTTPException(status_code=409, detail="At least one prompt must remain")
        if read_env_values().get("AGENT_PROMPT_ID", "flora-healthcare-agent-v1") == prompt_id:
            raise HTTPException(status_code=409, detail="Select another active prompt before deleting this one")
        remaining = [prompt for prompt in prompts if prompt["id"] != prompt_id]
        if len(remaining) == len(prompts):
            raise HTTPException(status_code=404, detail="Prompt not found")
        save_prompts(remaining)


@app.post("/developer/prompts/preview")
def preview_developer_prompt(
    request: PromptPreviewRequest,
    _: dict[str, str] = Depends(require_dashboard_session),
) -> dict[str, str]:
    validate_prompt_template(request.template)
    sample_values = {
        "patient_id": "patient-001",
        "patient_name": "Sample Patient",
        "glucose_mg_dl": "110",
        "hba1c_percent": "6.1",
    }
    rendered = request.template
    for key, value in sample_values.items():
        rendered = rendered.replace(f"{{{key}}}", value).replace(f"{{{{{key}}}}}", value)
    return {"preview": rendered}


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


def read_env_values() -> dict[str, str]:
    if not ENV_PATH.exists():
        return {}
    values: dict[str, str] = {}
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key] = value
    return values


def save_env_values(updates: dict[str, str]) -> None:
    existing_lines = ENV_PATH.read_text(encoding="utf-8").splitlines() if ENV_PATH.exists() else []
    seen: set[str] = set()
    output: list[str] = []
    for line in existing_lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0]
            if key in updates:
                output.append(f"{key}={updates[key]}")
                seen.add(key)
                continue
        output.append(line)
    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")
    temporary_path = ENV_PATH.with_suffix(".env.tmp")
    temporary_path.write_text("\n".join(output) + "\n", encoding="utf-8")
    os.replace(temporary_path, ENV_PATH)


def mask_secret(value: str) -> str:
    if not value:
        return ""
    return f"{value[:3]}****{value[-2:]}" if len(value) > 5 else "****"


def config_payload() -> list[dict[str, str | bool]]:
    values = read_env_values()
    return [
        {
            "key": key,
            "value": "" if key in CONFIG_SECRET_KEYS else values.get(key, ""),
            "configured": bool(values.get(key)),
            "secret": key in CONFIG_SECRET_KEYS,
            "masked": mask_secret(values.get(key, "")) if key in CONFIG_SECRET_KEYS else "",
        }
        for key in CONFIG_KEYS
    ]


def load_prompts() -> list[dict]:
    with PROMPTS_PATH.open(encoding="utf-8") as prompts_file:
        return json.load(prompts_file)


def save_prompts(prompts: list[dict]) -> None:
    temporary_path = PROMPTS_PATH.with_suffix(".json.tmp")
    with temporary_path.open("w", encoding="utf-8") as prompts_file:
        json.dump(prompts, prompts_file, indent=2)
        prompts_file.write("\n")
    os.replace(temporary_path, PROMPTS_PATH)


def validate_prompt_template(template: str) -> None:
    variables = set(re.findall(r"(?<!\{)\{([A-Za-z0-9_]+)\}(?!\})", template))
    unsupported = variables - SUPPORTED_PROMPT_VARIABLES
    if unsupported:
        names = ", ".join(sorted(unsupported))
        raise HTTPException(status_code=422, detail=f"Unsupported prompt variables: {names}")


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

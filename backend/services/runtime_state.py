"""Shared in-process state for the JSON-backed API."""

from pathlib import Path
from threading import Lock

from services.file_store import load_json, save_json

BASE_DIR = Path(__file__).parents[1]
PATIENTS_PATH = BASE_DIR / "patients.json"
SLOTS_PATH = BASE_DIR / "slots.json"
BOOKED_SLOTS: set[str] = set()
BOOKING_LOCK = Lock()
PATIENTS_LOCK = Lock()
SLOTS_LOCK = Lock()


def load_patients() -> list[dict]:
    return load_json(PATIENTS_PATH)


def save_patients(patients: list[dict]) -> None:
    save_json(PATIENTS_PATH, patients)


def load_slots() -> list[dict]:
    return load_json(SLOTS_PATH)


def save_slots(slots: list[dict]) -> None:
    save_json(SLOTS_PATH, slots)

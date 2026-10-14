"""Validation shared by API routes and outbound-call commands."""

import re
from urllib.parse import urlparse

from fastapi import HTTPException

E164_PHONE_PATTERN = re.compile(r"^\+[1-9]\d{6,14}$")


def normalize_phone(phone: str) -> str:
    normalized = phone.replace(" ", "").replace("-", "").replace("(", "").replace(")", "")
    if not E164_PHONE_PATTERN.fullmatch(normalized):
        raise HTTPException(
            status_code=422,
            detail="Phone must use international format, for example +919876543210",
        )
    return normalized


def validate_url(value: str, key: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail=f"{key} must be a valid URL")


def validate_e164_phone(phone: str) -> bool:
    return bool(E164_PHONE_PATTERN.fullmatch(phone))

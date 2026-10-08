import argparse
import asyncio
import json
import os
import re
import uuid
from pathlib import Path

from dotenv import load_dotenv
from livekit import api

from voice_agent import AGENT_NAME, load_patient

load_dotenv(Path(__file__).with_name(".env"))
E164 = re.compile(r"^\+[1-9]\d{7,14}$")


async def dispatch_call(patient_id: str, phone_number: str) -> str:
    load_patient(patient_id)
    missing = [
        name
        for name in (
            "LIVEKIT_URL",
            "LIVEKIT_API_KEY",
            "LIVEKIT_API_SECRET",
            "SIP_OUTBOUND_TRUNK_ID",
        )
        if not os.getenv(name)
    ]
    if missing:
        raise SystemExit(f"Missing required settings in .env: {', '.join(missing)}")

    room_name = f"call-{patient_id}-{uuid.uuid4().hex[:8]}"
    async with api.LiveKitAPI() as lkapi:
        dispatch = await lkapi.agent_dispatch.create_dispatch(
            api.CreateAgentDispatchRequest(
                agent_name=AGENT_NAME,
                room=room_name,
                metadata=json.dumps(
                    {"patient_id": patient_id, "phone_number": phone_number}
                ),
            )
        )
    return dispatch.room


async def place_call(patient_id: str, phone_number: str) -> None:
    room_name = await dispatch_call(patient_id, phone_number)
    print(f"Dispatched one call to {phone_number} in room {room_name}.")
    print("Watch the agent worker terminal for call progress.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Place one outbound test call.")
    parser.add_argument("patient_id", help="Patient ID from patients.json")
    parser.add_argument("phone_number", help="Test destination in E.164, e.g. +14155550123")
    args = parser.parse_args()
    if not E164.match(args.phone_number):
        raise SystemExit("phone_number must be E.164 format, e.g. +14155550123")
    asyncio.run(place_call(args.patient_id, args.phone_number))


if __name__ == "__main__":
    main()

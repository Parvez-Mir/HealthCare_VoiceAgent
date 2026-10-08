import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from call_capture import start_call_capture
from livekit import api
from livekit.agents import (
    Agent,
    AgentServer,
    AgentSession,
    JobContext,
    cli,
    function_tool,
    room_io,
)
from livekit.agents.types import APIConnectOptions
from livekit.agents.voice.agent_session import SessionConnectOptions
from livekit.agents.voice.turn import (
    InterruptionOptions,
    PreemptiveGenerationOptions,
    TurnHandlingOptions,
)
from livekit.plugins import assemblyai, cartesia, noise_cancellation, openai, silero


load_dotenv(Path(__file__).with_name(".env"))
logger = logging.getLogger("healthcare-voice-agent")
PATIENTS_PATH = Path(__file__).with_name("patients.json")
DEFAULT_BACKEND_URL = "http://127.0.0.1:8000"
AGENT_NAME = "healthcare-agent"
server = AgentServer()


def load_patient(patient_id: str) -> dict[str, Any]:
    with PATIENTS_PATH.open(encoding="utf-8") as patients_file:
        patients = json.load(patients_file)

    for patient in patients:
        if patient["id"] == patient_id:
            return patient
    raise ValueError(f"Patient '{patient_id}' was not found in {PATIENTS_PATH}")


def patient_instructions(patient: dict[str, Any]) -> str:
    biomarkers = patient["biomarkers"]
    return f"""
You are a friendly, concise healthcare appointment assistant.
You are speaking with {patient["name"]}, whose identity has already been loaded
from the clinic's dummy patient records. Confirm their name before discussing
their results.

The patient's recorded biomarkers are:
- Blood glucose: {biomarkers["glucose_mg_dl"]} mg/dL
- HbA1c: {biomarkers["hba1c_percent"]}%

Only state those exact values. Do not diagnose, speculate, or invent medical
advice. Explain that a clinician should interpret the results. Offer to arrange
a consultation, and use the booking tools when the patient agrees. If the
patient declines, thank them and end the conversation politely. Keep each
spoken response to one or two short sentences unless the patient asks for more
detail.
""".strip()


class HealthcareAgent(Agent):
    def __init__(self, patient: dict[str, Any], backend_url: str) -> None:
        super().__init__(instructions=patient_instructions(patient))
        self._backend_url = backend_url.rstrip("/")
        self._patient_id = patient["id"]

    @function_tool(
        description="Check the fake consultation slots currently available."
    )
    async def check_available_slots(self) -> str:
        logger.info("Calling GET %s/slots", self._backend_url)
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{self._backend_url}/slots", timeout=10)
            response.raise_for_status()
        slots = response.json()
        logger.info("Available slots result: %s", slots)
        return json.dumps(slots)

    @function_tool(
        description="Book a consultation for this patient using an available slot ID."
    )
    async def book_appointment(self, slot_id: str) -> str:
        payload = {"patient_id": self._patient_id, "slot_id": slot_id}
        logger.info("Calling POST %s/appointments with %s", self._backend_url, payload)
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{self._backend_url}/appointments",
                json=payload,
                timeout=10,
            )
            response.raise_for_status()
        booking = response.json()
        logger.info("Booking result: %s", booking)
        return json.dumps(booking)


def read_call_request(ctx: JobContext) -> dict[str, Any]:
    if not ctx.job.metadata:
        return {}
    try:
        request = json.loads(ctx.job.metadata)
    except json.JSONDecodeError as error:
        raise RuntimeError("Dispatch metadata is not valid JSON") from error
    return request if isinstance(request, dict) else {}


async def dial_patient(ctx: JobContext, phone_number: str) -> None:
    trunk_id = os.getenv("SIP_OUTBOUND_TRUNK_ID")
    if not trunk_id:
        raise RuntimeError("SIP_OUTBOUND_TRUNK_ID is required for outbound calls")
    logger.info("Dialing %s through trunk %s", phone_number, trunk_id)
    try:
        await ctx.api.sip.create_sip_participant(
            api.CreateSIPParticipantRequest(
                room_name=ctx.room.name,
                sip_trunk_id=trunk_id,
                sip_call_to=phone_number,
                participant_identity=f"phone-{phone_number}",
                participant_name="Patient",
                wait_until_answered=True,
            )
        )
    except api.TwirpError as error:
        sip_status = error.metadata.get("sip_status_code", "unknown")
        raise RuntimeError(
            f"Outbound call failed: {error.message} (SIP status {sip_status})"
        ) from error
    logger.info("Call answered by %s", phone_number)


@server.rtc_session(agent_name=AGENT_NAME)
async def entrypoint(ctx: JobContext) -> None:
    call_request = read_call_request(ctx)
    phone_number = call_request.get("phone_number")
    patient_id = call_request.get("patient_id") or os.getenv(
        "PATIENT_ID", "patient-001"
    )
    patient = load_patient(patient_id)
    backend_url = os.getenv("BACKEND_URL", DEFAULT_BACKEND_URL)
    assemblyai_api_key = os.getenv("ASSEMBLYAI_API_KEY")
    if not assemblyai_api_key:
        raise RuntimeError("ASSEMBLYAI_API_KEY is required to start the voice agent")
    cartesia_api_key = os.getenv("CARTESIA_API_KEY")
    if not cartesia_api_key:
        raise RuntimeError("CARTESIA_API_KEY is required to start the voice agent")
    ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1")

    await ctx.connect()
    if phone_number:
        try:
            await dial_patient(ctx, phone_number)
        except RuntimeError:
            logger.exception("Outbound call was not connected; ending the job")
            ctx.shutdown()
            return
    session = AgentSession(
        stt=assemblyai.STT(
            api_key=assemblyai_api_key,
            model="universal-3-6-pro",
            mode="min_latency",
        ),
        llm=openai.LLM(
            model=ollama_model,
            api_key="ollama",
            base_url=ollama_base_url,
            temperature=0.2,
            max_completion_tokens=256,
        ),
        tts=cartesia.TTS(
            api_key=cartesia_api_key,
            model="sonic-3",
        ),
        vad=silero.VAD.load(),
        turn_handling=TurnHandlingOptions(
            interruption=InterruptionOptions(
                enabled=True,
                mode="vad",
                min_duration=0.15,
                min_words=0,
                resume_false_interruption=True,
            ),
            preemptive_generation=PreemptiveGenerationOptions(enabled=False),
        ),
        conn_options=SessionConnectOptions(
            llm_conn_options=APIConnectOptions(
                max_retry=0,
                timeout=60,
            ),
        ),
    )
    await session.start(
        agent=HealthcareAgent(patient, backend_url),
        room=ctx.room,
        room_options=room_io.RoomOptions(
            audio_input=room_io.AudioInputOptions(
                noise_cancellation=(
                    noise_cancellation.BVCTelephony()
                    if phone_number
                    else noise_cancellation.BVC()
                ),
            ),
        ),
    )
    await start_call_capture(
        ctx,
        session,
        {
            "patient_id": patient["id"],
            "patient_name": patient["name"],
            "phone_number": phone_number,
            "biomarkers": patient["biomarkers"],
        },
    )
    await session.generate_reply(
        instructions=(
            f"Greet {patient['name']}, confirm their identity, and explain that "
            "you can review their recorded biomarkers and arrange a consultation."
        )
    )


if __name__ == "__main__":
    cli.run_app(server)

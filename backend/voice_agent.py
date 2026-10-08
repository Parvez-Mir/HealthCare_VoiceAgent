import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import dotenv_values, load_dotenv
from call_capture import CallCapture
from opik_integration import setup_live_tracing
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
from livekit.plugins import (
    anthropic,
    assemblyai,
    cartesia,
    google,
    noise_cancellation,
    openai,
    silero,
)


ENV_PATH = Path(__file__).with_name(".env")
load_dotenv(ENV_PATH, override=True)
logger = logging.getLogger("healthcare-voice-agent")
# Cartesia "Fiona - Witty Woman"
DEFAULT_CARTESIA_VOICE_ID = "a01c369f-6d2d-4185-bc20-b32c225eab70"
PATIENTS_PATH = Path(__file__).with_name("patients.json")
AGENT_PROMPTS_PATH = Path(__file__).with_name("agent_prompts.json")
DEFAULT_AGENT_PROMPT_ID = "just_testing_prompt"
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


def load_runtime_config() -> dict[str, str]:
    values = {
        key: value
        for key, value in dotenv_values(ENV_PATH).items()
        if value is not None
    }
    return {key: str(value) for key, value in values.items()}


def create_llm(config: dict[str, str]):
    provider = (config.get("LLM_PROVIDER") or "ollama").strip().lower()
    model = config.get("LLM_MODEL") or config.get("OLLAMA_MODEL") or "qwen2.5:7b"
    api_key = config.get("LLM_API_KEY", "")
    if provider == "ollama":
        return openai.LLM(
            model=model,
            api_key=api_key or "ollama",
            base_url=config.get("LLM_BASE_URL") or config.get("OLLAMA_BASE_URL")
            or "http://127.0.0.1:11434/v1",
            temperature=0.1,
            max_completion_tokens=256,
        )
    if provider == "openai":
        if not api_key:
            raise RuntimeError("LLM_API_KEY is required for the OpenAI provider")
        return openai.LLM(
            model=model,
            api_key=api_key,
            base_url=config.get("LLM_BASE_URL") or "https://api.openai.com/v1",
            temperature=0.1,
            max_completion_tokens=256,
        )
    if provider == "google":
        if not api_key:
            raise RuntimeError("LLM_API_KEY is required for the Google provider")
        return google.LLM(
            model=model,
            api_key=api_key,
            temperature=0.1,
            max_output_tokens=256,
        )
    if provider == "anthropic":
        if not api_key:
            raise RuntimeError("LLM_API_KEY is required for the Anthropic provider")
        return anthropic.LLM(
            model=model,
            api_key=api_key,
            temperature=0.1,
            max_tokens=256,
        )
    raise RuntimeError(
        "Unsupported LLM_PROVIDER. Choose ollama, openai, google, or anthropic."
    )


def load_agent_prompt(
    prompt_id: str | None = None, config: dict[str, str] | None = None
) -> tuple[str, str]:
    runtime_config = config or load_runtime_config()
    selected_id = prompt_id or runtime_config.get("AGENT_PROMPT_ID") or DEFAULT_AGENT_PROMPT_ID
    with AGENT_PROMPTS_PATH.open(encoding="utf-8") as prompts_file:
        prompts = json.load(prompts_file)

    for prompt in prompts:
        if prompt.get("id") == selected_id:
            template = prompt.get("template")
            if not isinstance(template, str):
                raise ValueError(
                    f"Prompt '{selected_id}' has no valid template in "
                    f"{AGENT_PROMPTS_PATH}"
                )
            return selected_id, template
    raise ValueError(f"Prompt '{selected_id}' was not found in {AGENT_PROMPTS_PATH}")


def patient_instructions(
    patient: dict[str, Any], prompt_id: str, config: dict[str, str]
) -> str:
    biomarkers = patient["biomarkers"]
    _, template = load_agent_prompt(prompt_id, config)
    return template.format(
        patient_id=patient["id"],
        patient_name=patient["name"],
        glucose_mg_dl=biomarkers["glucose_mg_dl"],
        hba1c_percent=biomarkers["hba1c_percent"],
    )


class HealthcareAgent(Agent):
    def __init__(
        self,
        patient: dict[str, Any],
        backend_url: str,
        prompt_id: str,
        config: dict[str, str],
    ) -> None:
        super().__init__(instructions=patient_instructions(patient, prompt_id, config))
        self._backend_url = backend_url.rstrip("/")
        self._patient_id = patient["id"]
        self._patient_name = patient["name"]
        self._identity_verified = False

    @function_tool(
        description=(
            "Verify the caller's patient ID and full patient name against the "
            "clinic record before any patient information or booking tools are used."
        )
    )
    async def verify_patient_identity(
        self, patient_id: str, patient_name: str
    ) -> str:
        verified = (
            patient_id.strip() == self._patient_id
            and patient_name.strip().casefold() == self._patient_name.casefold()
        )
        if verified:
            self._identity_verified = True
            return json.dumps({"verified": True})
        return json.dumps(
            {
                "verified": False,
                "message": "Patient ID and patient name could not be verified.",
            }
        )

    @function_tool(
        description="Check the fake consultation slots currently available."
    )
    async def check_available_slots(self) -> str:
        if not self._identity_verified:
            return json.dumps(
                {
                    "error": "identity_verification_required",
                    "message": "Verify the patient ID and name before checking slots.",
                }
            )
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
        if not self._identity_verified:
            return json.dumps(
                {
                    "error": "identity_verification_required",
                    "message": "Verify the patient ID and name before booking.",
                }
            )
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
    load_dotenv(ENV_PATH, override=True)
    runtime_config = load_runtime_config()
    call_request = read_call_request(ctx)
    phone_number = call_request.get("phone_number")
    patient_id = call_request.get("patient_id") or runtime_config.get("PATIENT_ID") or "patient-001"
    patient = load_patient(patient_id)
    setup_live_tracing(ctx, patient_id)
    backend_url = runtime_config.get("BACKEND_URL") or DEFAULT_BACKEND_URL
    assemblyai_api_key = runtime_config.get("ASSEMBLYAI_API_KEY")
    if not assemblyai_api_key:
        raise RuntimeError("ASSEMBLYAI_API_KEY is required to start the voice agent")
    cartesia_api_key = runtime_config.get("CARTESIA_API_KEY")
    if not cartesia_api_key:
        raise RuntimeError("CARTESIA_API_KEY is required to start the voice agent")
    llm_provider = runtime_config.get("LLM_PROVIDER") or "ollama"
    llm_model = runtime_config.get("LLM_MODEL") or runtime_config.get("OLLAMA_MODEL") or "qwen2.5:7b"
    llm_base_url = runtime_config.get("LLM_BASE_URL") or runtime_config.get("OLLAMA_BASE_URL") or ""
    cartesia_voice_id = runtime_config.get("CARTESIA_VOICE_ID") or DEFAULT_CARTESIA_VOICE_ID
    agent_prompt_id = load_agent_prompt(config=runtime_config)[0]
    logger.info(
        "Using call configuration: provider=%s prompt=%s model=%s voice=%s",
        llm_provider,
        agent_prompt_id,
        llm_model,
        cartesia_voice_id,
    )
    config_snapshot = {
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "llm_api_key_configured": bool(runtime_config.get("LLM_API_KEY")),
        "ollama_model": llm_model,
        "ollama_base_url": llm_base_url,
        "cartesia_voice_id": cartesia_voice_id,
        "agent_prompt_id": agent_prompt_id,
        "backend_url": backend_url,
        "assemblyai_configured": bool(assemblyai_api_key),
        "cartesia_configured": bool(cartesia_api_key),
    }

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
        llm=create_llm(runtime_config),
        tts=cartesia.TTS(
            api_key=cartesia_api_key,
            model="sonic-3",
            voice=cartesia_voice_id,
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
    capture = CallCapture(
        ctx,
        session,
        {
            "patient_id": patient["id"],
            "patient_name": patient["name"],
            "phone_number": phone_number,
            "biomarkers": patient["biomarkers"],
            "agent_prompt_id": agent_prompt_id,
            "config_snapshot": config_snapshot,
        },
    )
    await session.start(
        agent=HealthcareAgent(patient, backend_url, agent_prompt_id, runtime_config),
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
    await capture.start_recording()
    await session.generate_reply(
        instructions=(
            "Start the conversation using the active system prompt. Follow "
            "that prompt's persona, opening, and conversation rules exactly. "
            "Do not add instructions from another prompt."
        )
    )


if __name__ == "__main__":
    cli.run_app(server)

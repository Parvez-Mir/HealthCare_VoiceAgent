import argparse
import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))
logger = logging.getLogger("healthcare-voice-agent")

OUTCOMES = {"booked", "declined", "interested_not_booked", "undecided", "no_conversation"}
LLM_OUTCOMES = {"declined", "interested_not_booked", "undecided"}
SYSTEM_PROMPT = """You analyze a phone call between a healthcare appointment
assistant (agent) and a patient. You are told whether the booking system
recorded an appointment. Reply with only JSON of the form
{"outcome": "<declined|interested_not_booked|undecided>",
"agent_claimed_booking": <true|false>, "summary": "<one or two sentences>"}.

outcome:
- declined: the patient clearly refused a consultation.
- interested_not_booked: the patient wanted or agreed to a consultation but no
  appointment was recorded.
- undecided: the patient neither agreed nor refused.
agent_claimed_booking: true if any agent message says an appointment is booked,
scheduled, or confirmed for the patient (for example "you are booked" or
"your appointment is confirmed"); false if the agent only offered or listed
slots. Judge this from the agent's words, not from the booking system.
Describe only what is in the transcript; never invent details."""


def booking_succeeded(tool_calls: list[dict[str, Any]]) -> tuple[bool, str | None]:
    """The booking tool result is the source of truth for appointment_booked."""
    for call in tool_calls:
        if call["name"] != "book_appointment" or call.get("is_error"):
            continue
        try:
            result = json.loads(call["result"])
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(result, dict) and result.get("status") == "booked":
            return True, result.get("confirmation_id")
    return False, None


async def _ask_llm(call: dict[str, Any], booked: bool) -> dict[str, Any]:
    base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/")
    transcript = "\n".join(f"{t['role']}: {t['text']}" for t in call["transcript"])
    tools = "\n".join(
        f"{t['name']}({t['arguments']}) -> {t['result']}" for t in call["tool_calls"]
    )
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{base_url}/chat/completions",
            json={
                "model": os.getenv("OLLAMA_MODEL", "qwen2.5:7b"),
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": f"Booking system recorded an appointment: {'yes' if booked else 'no'}\n\n"
                        f"Transcript:\n{transcript}\n\nTool calls:\n{tools or 'none'}",
                    },
                ],
            },
            timeout=120,
        )
        response.raise_for_status()
    return json.loads(response.json()["choices"][0]["message"]["content"])


async def analyze_call(call: dict[str, Any]) -> dict[str, Any]:
    booked, confirmation_id = booking_succeeded(call["tool_calls"])
    has_patient_speech = any(t["role"] == "patient" for t in call["transcript"])
    analysis: dict[str, Any] = {
        "appointment_booked": booked,
        "confirmation_id": confirmation_id,
        "outcome": "booked" if booked else "no_conversation",
        "summary": None,
        "agent_claimed_booking": None,
        "claim_matches_tool_result": None,
        "analysis_error": None,
    }
    if not has_patient_speech and not booked:
        analysis["summary"] = "The patient never spoke; the call was not answered or connected."
        return analysis

    try:
        llm_result = await _ask_llm(call, booked)
        summary = llm_result.get("summary")
        analysis["summary"] = summary if isinstance(summary, str) else None
        claimed = llm_result.get("agent_claimed_booking")
        if isinstance(claimed, bool):
            analysis["agent_claimed_booking"] = claimed
            analysis["claim_matches_tool_result"] = claimed == booked
        if not booked:
            outcome = llm_result.get("outcome")
            analysis["outcome"] = outcome if outcome in LLM_OUTCOMES else "undecided"
    except Exception as error:
        logger.exception("Post-call analysis model failed")
        analysis["analysis_error"] = f"{type(error).__name__}: {error}"
        if not booked:
            analysis["outcome"] = "undecided"
    return analysis


async def analyze_call_dir(call_dir: Path) -> dict[str, Any] | None:
    """Write analysis.json next to call.json. Never raises."""
    try:
        call = json.loads((call_dir / "call.json").read_text(encoding="utf-8"))
        analysis = await analyze_call(call)
        (call_dir / "analysis.json").write_text(
            json.dumps(analysis, indent=2), encoding="utf-8"
        )
        logger.info(
            "Post-call analysis for %s: appointment_booked=%s outcome=%s",
            call_dir.name,
            analysis["appointment_booked"],
            analysis["outcome"],
        )
        return analysis
    except Exception:
        logger.exception("Could not complete post-call analysis for %s", call_dir)
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Analyze a saved call folder.")
    parser.add_argument("call_dir", type=Path, help="e.g. calls/call-patient-001-abc")
    result = asyncio.run(analyze_call_dir(parser.parse_args().call_dir))
    print(json.dumps(result, indent=2))

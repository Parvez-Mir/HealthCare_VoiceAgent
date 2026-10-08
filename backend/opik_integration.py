"""All Opik code lives here. Sends one trace per saved call folder.

Failures are caught and logged; this must never affect a live call.
"""
import argparse
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv(Path(__file__).with_name(".env"))
logger = logging.getLogger("healthcare-voice-agent")


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def send_call_to_opik(call_dir: Path) -> str | None:
    """Log the call in call_dir as one Opik trace and return its trace ID."""
    try:
        import opik

        call = json.loads((call_dir / "call.json").read_text(encoding="utf-8"))
        analysis_path = call_dir / "analysis.json"
        analysis = (
            json.loads(analysis_path.read_text(encoding="utf-8"))
            if analysis_path.exists()
            else None
        )
        variables = {
            key: call.get(key)
            for key in ("patient_id", "patient_name", "phone_number", "biomarkers")
        }
        client = opik.Opik()
        trace = client.trace(
            name=f"call-{call.get('patient_id')}",
            start_time=_parse_time(call.get("started_at")),
            end_time=_parse_time(call.get("ended_at")),
            input={"call_variables": variables, "transcript": call["transcript"]},
            output={"analysis": analysis},
            metadata={
                "room": call.get("room"),
                "recording_path": call.get("recording_path"),
                "tool_calls": call["tool_calls"],
                "analysis": analysis,
                **variables,
            },
            tags=["outbound-call"],
        )
        for tool_call in call["tool_calls"]:
            trace.span(
                name=tool_call["name"],
                type="tool",
                start_time=_parse_time(tool_call.get("at")),
                end_time=_parse_time(tool_call.get("at")),
                input={"arguments": tool_call["arguments"]},
                output={"result": tool_call["result"]},
                error_info=(
                    {"exception_type": "ToolError", "traceback": tool_call["result"]}
                    if tool_call.get("is_error")
                    else None
                ),
            )
        if analysis:
            scores = []
            if analysis.get("claim_matches_tool_result") is not None:
                scores.append(
                    {
                        "name": "booking_claim_matches_tool_result",
                        "value": 1.0 if analysis["claim_matches_tool_result"] else 0.0,
                    }
                )
            scores.append(
                {
                    "name": "appointment_booked",
                    "value": 1.0 if analysis["appointment_booked"] else 0.0,
                }
            )
            for score in scores:
                trace.log_feedback_score(name=score["name"], value=score["value"])
        client.flush()
        logger.info("Sent call %s to Opik (trace %s)", call_dir.name, trace.id)
        return trace.id
    except Exception:
        logger.exception("Could not send call %s to Opik", call_dir)
        return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Send a saved call folder to Opik.")
    parser.add_argument("call_dir", type=Path, help="e.g. calls/call-patient-001-abc")
    print(send_call_to_opik(parser.parse_args().call_dir))

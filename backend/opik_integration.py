"""All Opik code lives here. Sends one trace per saved call folder.

Failures are caught and logged; this must never affect a live call.
"""
import argparse
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from workers.latency_metrics import extract_latency_metrics

load_dotenv(Path(__file__).with_name(".env"), override=True)
logger = logging.getLogger("healthcare-voice-agent")


def setup_live_tracing(ctx: Any, patient_id: str) -> None:
    """Export LiveKit's built-in OpenTelemetry spans (STT/LLM/TTS timings) to
    Opik live. No-op without Opik credentials; never raises."""
    import os

    api_key = os.getenv("OPIK_API_KEY")
    if not api_key:
        return
    try:
        from livekit.agents.telemetry import set_tracer_provider
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        base = os.getenv("OPIK_URL_OVERRIDE", "https://www.comet.com/opik/api")
        exporter = OTLPSpanExporter(
            timeout=30,
            endpoint=f"{base.rstrip('/')}/v1/private/otel/v1/traces",
            headers={
                "Authorization": api_key,
                "Comet-Workspace": os.getenv("OPIK_WORKSPACE", "default"),
                "projectName": os.getenv(
                    "OPIK_PROJECT_NAME", "healthcare-voice-agent"
                ),
            },
        )
        provider = TracerProvider()
        provider.add_span_processor(BatchSpanProcessor(exporter))
        set_tracer_provider(
            provider,
            metadata={
                "livekit.session.id": ctx.room.name,
                "patient_id": patient_id,
            },
        )

        async def flush() -> None:
            provider.force_flush()

        ctx.add_shutdown_callback(flush)
    except Exception:
        logger.exception("Could not set up live Opik tracing; continuing without it")


def _parse_time(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


def _turn_latencies(transcript: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per agent reply: stt_latency, llm_latency, tts_latency, e2e_latency (seconds).

    LiveKit stores STT on the patient message and LLM/TTS/e2e on the agent
    message, so STT comes from the patient turn that triggered the reply.
    Missing values are omitted, never reported as zero.
    """
    turns: list[dict[str, Any]] = []
    pending_stt: float | None = None
    for turn_number, message in enumerate(transcript, start=1):
        raw = extract_latency_metrics(message.get("metrics"))
        if message["role"] == "patient":
            if raw.get("transcription_delay"):
                pending_stt = raw["transcription_delay"]
            continue
        values = {
            "stt_latency": pending_stt,
            "llm_latency": raw.get("llm_node_ttft"),
            "tts_latency": raw.get("tts_node_ttfb"),
            "e2e_latency": raw.get("e2e_latency"),
        }
        pending_stt = None
        metrics = {k: round(v, 3) for k, v in values.items() if v is not None}
        if metrics:
            turns.append({"turn": turn_number, "message": message, "metrics": metrics})
    return turns


def _latency_summary(turns: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    """Average and max (seconds) of each metric over the turns that have it."""
    summary: dict[str, dict[str, float]] = {}
    for name in ("stt_latency", "llm_latency", "tts_latency", "e2e_latency"):
        values = [t["metrics"][name] for t in turns if name in t["metrics"]]
        if values:
            summary[name] = {
                "avg": round(sum(values) / len(values), 3),
                "max": round(max(values), 3),
                "turns": len(values),
            }
    return summary


def _record_turn_latency_spans(trace: Any, turns: list[dict[str, Any]]) -> None:
    for turn in turns:
        message = turn["message"]
        metrics = turn["metrics"]
        started_speaking_at = _parse_time(message.get("speech_started_at"))
        e2e_latency = metrics.get("e2e_latency")
        end_time = started_speaking_at or _parse_time(message.get("at"))
        start_time = (
            end_time - timedelta(seconds=e2e_latency)
            if started_speaking_at is not None
            and isinstance(e2e_latency, (int, float))
            else end_time
        )
        trace.span(
            name=f"agent-turn-{turn['turn']}-latency",
            type="general",
            start_time=start_time,
            end_time=end_time,
            input={"role": "agent"},
            output=metrics,
            metadata={"unit": "seconds"},
            tags=["turn-latency", "agent"],
        )


def _record_cost_spans(trace: Any, analysis: dict[str, Any] | None) -> None:
    if not analysis:
        return
    estimate = analysis.get("cost_estimate")
    if not isinstance(estimate, dict):
        return
    for stage in estimate.get("stages", []):
        usage = stage.get("usage", {})
        opik_usage = None
        if stage.get("stage") == "llm":
            opik_usage = {
                "prompt_tokens": usage.get("input_tokens", 0),
                "completion_tokens": usage.get("output_tokens", 0),
                "total_tokens": usage.get("input_tokens", 0)
                + usage.get("output_tokens", 0),
            }
        span_options: dict[str, Any] = {
            "name": f"{stage.get('stage', 'unknown')}-usage-and-cost",
            "type": "general",
            "input": {"provider": stage.get("provider"), "model": stage.get("model")},
            "output": {
                "usage": usage,
                "estimated_cost_usd": stage.get("estimated_cost_usd"),
                "currency": estimate.get("currency", "USD"),
                "pricing_configured": stage.get("pricing_configured", False),
            },
            "metadata": {"cost_estimate": True},
            "tags": ["usage", "cost-estimate", str(stage.get("stage", "unknown"))],
        }
        if opik_usage is not None:
            span_options["usage"] = opik_usage
            span_options["provider"] = stage.get("provider")
            span_options["model"] = stage.get("model")
        if isinstance(stage.get("estimated_cost_usd"), (int, float)):
            span_options["total_cost"] = stage["estimated_cost_usd"]
        trace.span(**span_options)


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
        turn_latencies = _turn_latencies(call["transcript"])
        latency_summary = _latency_summary(turn_latencies)
        client = opik.Opik()
        trace = client.trace(
            name=f"call-{call.get('patient_id')}",
            start_time=_parse_time(call.get("started_at")),
            end_time=_parse_time(call.get("ended_at")),
            input={"call_variables": variables, "transcript": call["transcript"]},
            output={"analysis": analysis, "latency_seconds": latency_summary},
            metadata={
                "latency_seconds": latency_summary,
                "room": call.get("room"),
                "recording_path": call.get("recording_path"),
                "tool_calls": call["tool_calls"],
                "analysis": analysis,
                "config_snapshot": call.get("config_snapshot"),
                "cost_estimate": analysis.get("cost_estimate") if analysis else None,
                "evaluations": {
                    "PII_handling": analysis.get("PII_handling") if analysis else None,
                },
                **variables,
            },
            tags=["outbound-call"],
        )
        _record_turn_latency_spans(trace, turn_latencies)
        _record_cost_spans(trace, analysis)
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
            value = analysis.get("PII_handling")
            if isinstance(value, bool):
                trace.log_feedback_score(
                    name="PII_handling",
                    value=1.0 if value else 0.0,
                )
        for name, stats in latency_summary.items():
            trace.log_feedback_score(name=f"avg_{name}", value=stats["avg"])
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

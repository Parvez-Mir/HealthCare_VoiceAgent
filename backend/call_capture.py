import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from livekit.agents import AgentSession, JobContext
from livekit.agents.voice.events import (
    ConversationItemAddedEvent,
    FunctionToolsExecutedEvent,
)
from livekit.agents.voice.recorder_io import RecorderIO

logger = logging.getLogger("healthcare-voice-agent")
CALLS_DIR = Path(__file__).with_name("calls")


def _iso(timestamp: float) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


async def start_call_capture(
    ctx: JobContext, session: AgentSession, metadata: dict[str, Any]
) -> Path:
    """Save audio and transcript under calls/<room>/. Never affects the live call.

    Layout: audio.ogg (stereo: caller left, agent right) and call.json
    (metadata, transcript, tool calls). Later phases add analysis.json here.
    """
    call_dir = CALLS_DIR / ctx.room.name
    audio_path = call_dir / "audio.ogg"
    call_path = call_dir / "call.json"
    started_at = time.time()
    transcript: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []

    def on_item(event: ConversationItemAddedEvent) -> None:
        item = event.item
        if getattr(item, "type", None) != "message" or item.role not in (
            "user",
            "assistant",
        ):
            return
        text = item.text_content
        if text:
            transcript.append(
                {
                    "role": "patient" if item.role == "user" else "agent",
                    "text": text,
                    "interrupted": item.interrupted,
                    "at": _iso(event.created_at),
                }
            )

    def on_tools(event: FunctionToolsExecutedEvent) -> None:
        for call, output in zip(event.function_calls, event.function_call_outputs):
            tool_calls.append(
                {
                    "name": call.name,
                    "arguments": call.arguments,
                    "result": output.output,
                    "is_error": output.is_error,
                    "at": _iso(event.created_at),
                }
            )

    session.on("conversation_item_added", on_item)
    session.on("function_tools_executed", on_tools)

    recorder: RecorderIO | None = None
    try:
        call_dir.mkdir(parents=True, exist_ok=True)
        recorder = RecorderIO(agent_session=session)
        session.input.audio = recorder.record_input(session.input.audio)
        session.output.audio = recorder.record_output(session.output.audio)
        await recorder.start(output_path=audio_path)
        logger.info("Capturing call to %s", call_dir)
    except Exception:
        logger.exception("Could not start call recording; continuing without it")
        recorder = None

    async def save() -> None:
        recording: str | None = None
        if recorder is not None:
            try:
                await recorder.aclose()
                recording = str(audio_path)
            except Exception:
                logger.exception("Could not finalize call recording")
        try:
            call_path.parent.mkdir(parents=True, exist_ok=True)
            call_path.write_text(
                json.dumps(
                    {
                        "room": ctx.room.name,
                        "started_at": _iso(started_at),
                        "ended_at": _iso(time.time()),
                        **metadata,
                        "recording_path": recording,
                        "transcript": transcript,
                        "tool_calls": tool_calls,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            logger.info("Saved call data to %s", call_dir)
        except Exception:
            logger.exception("Could not save call transcript")

    ctx.add_shutdown_callback(save)
    return call_dir

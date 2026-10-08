import json
import logging
import subprocess
import sys
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


class CallCapture:
    """Save audio and transcript under calls/<room>/. Never affects the live call.

    Layout: audio.ogg (stereo: caller left, agent right) and call.json
    (metadata, transcript, tool calls). Later phases add analysis.json here.

    Create it before session.start() so no early speech is missed, then call
    start_recording() after the session has started.
    """

    def __init__(
        self, ctx: JobContext, session: AgentSession, metadata: dict[str, Any]
    ) -> None:
        self._session = session
        self._metadata = metadata
        self._room = ctx.room.name
        self._call_dir = CALLS_DIR / self._room
        self._audio_path = self._call_dir / "audio.ogg"
        self._started_at = time.time()
        self._transcript: list[dict[str, Any]] = []
        self._tool_calls: list[dict[str, Any]] = []
        self._recorder: RecorderIO | None = None

        session.on("conversation_item_added", self._on_item)
        session.on("function_tools_executed", self._on_tools)
        ctx.add_shutdown_callback(self._save)

    def _on_item(self, event: ConversationItemAddedEvent) -> None:
        item = event.item
        if getattr(item, "type", None) != "message" or item.role not in (
            "user",
            "assistant",
        ):
            return
        text = item.text_content
        if text:
            self._transcript.append(
                {
                    "role": "patient" if item.role == "user" else "agent",
                    "text": text,
                    "interrupted": item.interrupted,
                    "at": _iso(event.created_at),
                }
            )

    def _on_tools(self, event: FunctionToolsExecutedEvent) -> None:
        for call, output in zip(event.function_calls, event.function_call_outputs):
            self._tool_calls.append(
                {
                    "name": call.name,
                    "arguments": call.arguments,
                    "result": output.output,
                    "is_error": output.is_error,
                    "at": _iso(event.created_at),
                }
            )

    async def start_recording(self) -> None:
        """Attach the recorder; the session's audio streams exist only after start."""
        try:
            self._call_dir.mkdir(parents=True, exist_ok=True)
            recorder = RecorderIO(agent_session=self._session)
            self._session.input.audio = recorder.record_input(self._session.input.audio)
            self._session.output.audio = recorder.record_output(
                self._session.output.audio
            )
            await recorder.start(output_path=self._audio_path)
            self._recorder = recorder
            logger.info("Capturing call to %s", self._call_dir)
        except Exception:
            logger.exception("Could not start call recording; continuing without it")

    async def _save(self) -> None:
        recording: str | None = None
        if self._recorder is not None:
            try:
                await self._recorder.aclose()
                recording = str(self._audio_path)
            except Exception:
                logger.exception("Could not finalize call recording")
        try:
            self._call_dir.mkdir(parents=True, exist_ok=True)
            (self._call_dir / "call.json").write_text(
                json.dumps(
                    {
                        "room": self._room,
                        "started_at": _iso(self._started_at),
                        "ended_at": _iso(time.time()),
                        **self._metadata,
                        "recording_path": recording,
                        "transcript": self._transcript,
                        "tool_calls": self._tool_calls,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            logger.info("Saved call data to %s", self._call_dir)
        except Exception:
            logger.exception("Could not save call transcript")
            return
        self._start_analysis()

    def _start_analysis(self) -> None:
        """Run the analysis in a detached process: the worker's shutdown window
        is short and a local model can take longer than that."""
        try:
            with (self._call_dir / "analysis.log").open("wb") as log:
                subprocess.Popen(
                    [
                        sys.executable,
                        str(Path(__file__).with_name("post_call_analysis.py")),
                        str(self._call_dir),
                    ],
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            logger.info("Started post-call analysis for %s", self._room)
        except Exception:
            logger.exception("Could not start post-call analysis")

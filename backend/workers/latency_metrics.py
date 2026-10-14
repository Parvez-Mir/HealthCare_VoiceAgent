"""Helpers for retaining LiveKit's per-message latency measurements."""

from typing import Any

LATENCY_METRIC_NAMES = {
    "transcription_delay",
    "end_of_turn_delay",
    "on_user_turn_completed_delay",
    "llm_node_ttft",
    "llm_node_tps",
    "llm_node_ttfs",
    "tts_node_ttfb",
    "playback_latency",
    "e2e_latency",
}


def extract_latency_metrics(metrics: object) -> dict[str, int | float]:
    if not isinstance(metrics, dict):
        return {}
    return {
        name: value
        for name, value in metrics.items()
        if name in LATENCY_METRIC_NAMES
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    }

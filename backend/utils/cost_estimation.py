"""Estimate per-stage provider costs from usage and explicitly configured rates."""

import math
from typing import Any

LLM_INPUT_RATE = "COST_LLM_INPUT_USD_PER_MILLION_TOKENS"
LLM_OUTPUT_RATE = "COST_LLM_OUTPUT_USD_PER_MILLION_TOKENS"
STT_RATE = "COST_STT_USD_PER_AUDIO_MINUTE"
TTS_RATE = "COST_TTS_USD_PER_1000_CHARACTERS"
RATE_KEYS = (LLM_INPUT_RATE, LLM_OUTPUT_RATE, STT_RATE, TTS_RATE)


def _configured_rate(rates: dict[str, str], key: str) -> float | None:
    value = rates.get(key, "").strip()
    if not value:
        return None
    try:
        rate = float(value)
    except ValueError:
        return None
    return rate if math.isfinite(rate) and rate >= 0 else None


def estimate_stage_costs(
    usage_records: list[dict[str, Any]],
    rates: dict[str, str],
    llm_provider: str | None = None,
) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []
    known_total = 0.0
    all_costs_known = True

    for record in usage_records:
        usage_type = record.get("type")
        stage: dict[str, Any] = {
            "stage": usage_type.removesuffix("_usage") if isinstance(usage_type, str) else "unknown",
            "provider": record.get("provider"),
            "model": record.get("model"),
            "usage": {},
            "estimated_cost_usd": None,
            "pricing_configured": False,
        }
        cost = 0.0
        unpriced_usage = False

        if usage_type == "llm_usage":
            input_tokens = record.get("input_tokens", 0)
            output_tokens = record.get("output_tokens", 0)
            stage["usage"] = {"input_tokens": input_tokens, "output_tokens": output_tokens}
            if (llm_provider or "").lower() == "ollama":
                stage["pricing_source"] = "local_inference_no_provider_token_charge"
            else:
                for amount, key in (
                    (input_tokens, LLM_INPUT_RATE),
                    (output_tokens, LLM_OUTPUT_RATE),
                ):
                    rate = _configured_rate(rates, key)
                    if amount and rate is None:
                        unpriced_usage = True
                    elif rate is not None:
                        cost += amount * rate / 1_000_000
        elif usage_type == "stt_usage":
            audio_seconds = record.get("audio_duration", 0)
            stage["usage"] = {"audio_seconds": audio_seconds}
            rate = _configured_rate(rates, STT_RATE)
            if audio_seconds and rate is None:
                unpriced_usage = True
            elif rate is not None:
                cost += audio_seconds * rate / 60
        elif usage_type == "tts_usage":
            characters = record.get("characters_count", 0)
            stage["usage"] = {
                "characters": characters,
                "audio_seconds": record.get("audio_duration", 0),
            }
            rate = _configured_rate(rates, TTS_RATE)
            if characters and rate is None:
                unpriced_usage = True
            elif rate is not None:
                cost += characters * rate / 1000
        else:
            stage["usage"] = {
                key: value
                for key, value in record.items()
                if isinstance(value, (int, float)) and not isinstance(value, bool)
            }
            unpriced_usage = bool(stage["usage"])

        if not unpriced_usage:
            stage["estimated_cost_usd"] = round(cost, 10)
            stage["pricing_configured"] = True
            known_total += cost
        else:
            all_costs_known = False
        stages.append(stage)

    reported_stages = {stage["stage"] for stage in stages}
    expected_stages = {"llm", "stt", "tts"}
    missing_usage_stages = sorted(expected_stages - reported_stages)
    estimate_complete = (
        not missing_usage_stages
        and all_costs_known
        and all(stage["pricing_configured"] for stage in stages)
    )
    return {
        "currency": "USD",
        "estimated_total_usd": round(known_total, 10) if estimate_complete else None,
        "known_stage_total_usd": round(known_total, 10),
        "estimate_complete": estimate_complete,
        "missing_usage_stages": missing_usage_stages,
        "stages": stages,
        "pricing_rates": {
            key: _configured_rate(rates, key) for key in RATE_KEYS
        },
    }

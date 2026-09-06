"""
strategy_insights — fan-facing narrative for a StrategyOutput.

Parallel to data_pipeline.ai_insights, and deliberately built the same way:
raw urllib call to the Gemini generateContent endpoint, certifi SSL context,
GEMINI_API_KEY / GEMINI_MODEL from the environment, failures logged and
swallowed so report generation can still finish.

This module ONLY narrates. It never runs or alters the simulator, and it never
picks a strategy — it explains the decision the simulator already made. If the
API key is missing or the call fails, it returns None and the caller falls back
to a deterministic markdown summary.
"""

from __future__ import annotations

import json
import os
import re
import ssl
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

import certifi
from dotenv import load_dotenv

from .models import StrategyOutput, to_report_json

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_SYSTEM_INSTRUCTION = (
    "You are an expert Formula 1 race strategist writing for an engaged fan. "
    "You are given a JSON object that a simulator has already produced: it contains "
    "the chosen headline strategy, alternatives, safety-car plan, weather sensitivity, "
    "beneficiaries, risk factors, confidence, data coverage and assumptions. "
    "Narrate ONLY what is in this JSON. You must NOT invent facts, lap times, driver "
    "names, weather, penalties, or telemetry that are not present. You must NOT choose "
    "or second-guess a strategy yourself — the simulator has already decided; you only "
    "explain its decision. Be precise with the compound sequence and pit windows given. "
    "Return GitHub-flavoured markdown only, with exactly these four section headings, in "
    "this order:\n"
    "## Strategy Recommendation\n## Why This Works\n## Risk Factors\n## Race Watch\n"
    "Keep it tight: a few sentences or short bullets under each heading. Reflect the "
    "stated confidence and call out assumptions honestly when relevant."
)


def generate_strategy_narrative(output: StrategyOutput) -> Optional[str]:
    """
    Turn a StrategyOutput into fan-facing markdown via Gemini.

    Returns the markdown string, or None if the key is missing or the call fails.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("Strategy narrative skipped: GEMINI_API_KEY is not set")
        return None

    model_name = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    payload = to_report_json(output)

    try:
        return _request_gemini_markdown(api_key, model_name, payload)
    except Exception as exc:  # noqa: BLE001 — mirror ai_insights: log and swallow
        print(f"Strategy narrative generation failed: {exc}")
        return None


def _request_gemini_markdown(api_key: str, model_name: str, payload: dict[str, Any]) -> str:
    prompt = (
        "Write the fan-facing strategy report from this simulator output JSON. "
        "Use the headlineStrategy compound sequence and pit windows verbatim in "
        "'Strategy Recommendation'. Ground 'Why This Works' in the reasoningInputs, "
        "beneficiaries and dataCoverage. Use riskFactors and weatherSensitivity for "
        "'Risk Factors'. Use safetyCarPlan and the pit windows for 'Race Watch'. "
        "Do not introduce any compound, lap number, or scenario not in the JSON.\n\n"
        f"{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"
    )
    request_body = {
        "system_instruction": {"parts": [{"text": _SYSTEM_INSTRUCTION}]},
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3},
    }

    request = urllib.request.Request(
        GEMINI_ENDPOINT.format(model=model_name),
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        method="POST",
    )

    ssl_context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urllib.request.urlopen(request, timeout=30, context=ssl_context) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API returned HTTP {exc.code}: {detail}") from exc

    text = (
        response_body.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [{}])[0]
        .get("text")
    )
    if not text:
        raise RuntimeError("Gemini API response did not include text")
    return _strip_code_fence(text).strip()


def _strip_code_fence(text: str) -> str:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:markdown)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned


def fallback_markdown(output: StrategyOutput) -> str:
    """
    Deterministic markdown used when the AI narrative is unavailable. Keeps the
    same four sections so the API contract is stable with or without Gemini.
    """
    h = output.headline_strategy
    seq = " → ".join(h.compound_sequence)
    windows = "; ".join(
        f"stop {w.stop_number} laps {w.earliest_lap}-{w.latest_lap} (onto {w.in_compound})"
        for w in h.pit_windows
    )
    risks = "\n".join(f"- {r}" for r in output.risk_factors) or "- None flagged."
    sc = "\n".join(
        f"- **{s.window_label}:** {s.recommended_action}"
        for s in output.safety_car_plan.scenarios
    )
    return (
        "## Strategy Recommendation\n"
        f"A {h.num_stops}-stop on **{seq}**. Pit windows: {windows}. "
        f"Modelled confidence {output.confidence:.0%}.\n\n"
        "## Why This Works\n"
        + "\n".join(f"- {r}" for r in h.reasoning_inputs)
        + "\n\n## Risk Factors\n"
        + risks
        + "\n\n## Race Watch\n"
        + (sc or "- Monitor the pit windows above for safety-car timing.")
    )

"""
FastAPI router for the Strategy Report feature.

Endpoints (mounted on the existing app via app.include_router):
  POST /strategy/next-race  — run the simulator for a race + stage, persist, return.
  GET  /strategy/next-race  — return the latest cached report for the next race.

Mirrors the existing /predict endpoints' contract style (no version prefix,
plain async handlers, HTTPException on failure). Reuses the shared Supabase
client; creates no new client or app.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, HTTPException

from . import data_access as da
from .degradation_model import DegradationModel
from .models import (
    DRY_COMPOUNDS,
    ReportStage,
    StrategyOutput,
    StrategyReportResponse,
    StrategyRequest,
    to_report_json,
)
from .strategy_insights import fallback_markdown, generate_strategy_narrative
from .strategy_simulator import MODEL_VERSION, SimulationInputs, simulate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strategy", tags=["strategy"])

_DEFAULT_TOTAL_LAPS = 55  # used only if a circuit has no lap count on record

# Tiny in-process cache for the fitted degradation model. Refit only when the
# number of stints changes (cheap heuristic; the table grows once per weekend).
_deg_cache: dict[str, Any] = {"key": None, "model": None}


# ── endpoints ──────────────────────────────────────────────────────────────

@router.post("/next-race", response_model=StrategyReportResponse)
async def post_next_race(request: StrategyRequest) -> StrategyReportResponse:
    """Generate (or return cached) a strategy report for a race + stage."""
    try:
        return _generate_report(request)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Strategy report generation failed")
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/next-race", response_model=StrategyReportResponse)
async def get_next_race() -> StrategyReportResponse:
    """Return the latest cached strategy report for the next upcoming race."""
    client = da.get_client()
    race_event_id = da.get_next_race_event_id(client)
    if race_event_id is None:
        raise HTTPException(status_code=404, detail="No upcoming race scheduled.")

    row = _latest_report_row(race_event_id, client)
    if row is None:
        return StrategyReportResponse(
            status="no_report",
            race_event_id=race_event_id,
            report_stage=ReportStage.PRE_WEEKEND,
            model_version=MODEL_VERSION,
            generated_at=datetime.now(timezone.utc).isoformat(),
            cached=False,
            summary=None,
            report=None,
        )
    return _response_from_row(row, cached=True)


# ── orchestration ────────────────────────────────────────────────────────────

def _generate_report(request: StrategyRequest) -> StrategyReportResponse:
    client = da.get_client()

    ctx = da.get_race_context(request.race_event_id, client)
    if ctx is None:
        raise HTTPException(
            status_code=404,
            detail=f"No race_event found for id {request.race_event_id}.",
        )

    circuit = ctx.get("circuits") or {}
    circuit_id = ctx.get("circuit_id") or circuit.get("id")
    total_laps = int(circuit.get("laps") or _DEFAULT_TOTAL_LAPS)

    profile = da.get_track_strategy_profile(circuit_id, client) if circuit_id else None
    entries = da.get_race_entries(request.race_event_id, client)
    stints = da.get_all_stints(client)

    deg_model = _get_deg_model(stints)
    ref_lap = _ref_lap_time(stints, circuit_id)

    inputs = SimulationInputs(
        race_event_id=request.race_event_id,
        circuit_id=circuit_id,
        total_laps=total_laps,
        report_stage=request.report_stage,
        deg_model=deg_model,
        profile=profile,
        entries=entries,
        available_compounds=DRY_COMPOUNDS,
        weather_rain_probability=(
            request.weather_forecast.rain_probability
            if request.weather_forecast else None
        ),
        grid_penalties=request.grid_penalties,
        ref_lap_time_s=ref_lap,
    )

    output, input_hash = simulate(inputs)

    # Cache hit: same inputs, not forced -> return the stored report.
    cached = da.get_cached_report(request.race_event_id, request.report_stage.value, client)
    if cached and cached.get("input_hash") == input_hash and not request.force_refresh:
        logger.info("Strategy report cache hit for race %s / %s",
                    request.race_event_id, request.report_stage.value)
        return _response_from_row(cached, cached=True)

    # Narrate (Gemini), falling back to deterministic markdown.
    summary = generate_strategy_narrative(output) or fallback_markdown(output)

    generated_at = datetime.now(timezone.utc).isoformat()
    row = {
        "race_event_id": request.race_event_id,
        "report_stage": request.report_stage.value,
        "model_version": MODEL_VERSION,
        "input_hash": input_hash,
        "summary": summary,
        "report_json": to_report_json(output),
        "generated_at": generated_at,
    }
    saved = da.upsert_report(row, client) or row

    return StrategyReportResponse(
        status="generated",
        race_event_id=request.race_event_id,
        report_stage=request.report_stage,
        model_version=MODEL_VERSION,
        generated_at=saved.get("generated_at", generated_at),
        cached=False,
        summary=summary,
        report=output,
    )


# ── helpers ────────────────────────────────────────────────────────────────

def _get_deg_model(stints: list[dict[str, Any]]) -> DegradationModel:
    key = len(stints)
    if _deg_cache["key"] != key or _deg_cache["model"] is None:
        _deg_cache["model"] = DegradationModel.fit(stints)
        _deg_cache["key"] = key
    return _deg_cache["model"]


def _ref_lap_time(stints: list[dict[str, Any]], circuit_id: Optional[int]) -> Optional[float]:
    """Fastest representative clean-air pace seen at this circuit (race-time anchor)."""
    if circuit_id is None:
        return None
    paces = [
        float(s["clean_air_pace"])
        for s in stints
        if s.get("clean_air_pace") is not None
        and (s.get("race_events") or {}).get("circuit_id") == circuit_id
    ]
    return min(paces) if paces else None


def _latest_report_row(race_event_id: int, client: Any) -> Optional[dict[str, Any]]:
    result = (
        client.table("strategy_reports")
        .select("*")
        .eq("race_event_id", race_event_id)
        .order("generated_at", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _response_from_row(row: dict[str, Any], cached: bool) -> StrategyReportResponse:
    report_json = row.get("report_json") or None
    report = StrategyOutput.model_validate(report_json) if report_json else None
    return StrategyReportResponse(
        status="cached" if cached else "generated",
        race_event_id=row["race_event_id"],
        report_stage=ReportStage(row["report_stage"]),
        model_version=row.get("model_version", MODEL_VERSION),
        generated_at=row.get("generated_at") or datetime.now(timezone.utc).isoformat(),
        cached=cached,
        summary=row.get("summary"),
        report=report,
    )

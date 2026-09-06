"""
Supabase reads and the strategy_reports cache for the Strategy Report feature.

Reuses data_pipeline.db.supabase_client.get_client() — no new client is created.
All functions accept an optional pre-built client so callers can share one.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Optional

from data_pipeline.db.supabase_client import get_client


# ── Race context ──────────────────────────────────────────────────────────

def get_race_context(race_event_id: int, client: Any = None) -> Optional[dict[str, Any]]:
    """
    Return the race_event joined to its circuit (the static profile inputs:
    laps, length, corners, plus the circuit id used for track_strategy_profiles).
    """
    client = client or get_client()
    result = (
        client.table("race_events")
        .select(
            "id,season,round,grand_prix_name,circuit_id,"
            "circuits(id,code,file_slug,title,subtitle,weekend_format,length_km,laps,corners)"
        )
        .eq("id", race_event_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def get_next_race_event_id(client: Any = None) -> Optional[int]:
    """
    The next upcoming race: the earliest 'race' session whose start is in the
    future. Falls back to None if no future race session is scheduled.
    """
    client = client or get_client()
    now = datetime.now(timezone.utc).isoformat()
    result = (
        client.table("race_sessions")
        .select("race_event_id,session_start_utc,session_type")
        .eq("session_type", "race")
        .gte("session_start_utc", now)
        .order("session_start_utc", desc=False)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]["race_event_id"]
    return None


# ── Track strategy profile ─────────────────────────────────────────────────

def get_track_strategy_profile(circuit_id: int, client: Any = None) -> Optional[dict[str, Any]]:
    client = client or get_client()
    result = (
        client.table("track_strategy_profiles")
        .select("*")
        .eq("circuit_id", circuit_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


# ── Historical stints (degradation / pit-loss training) ─────────────────────

_STINT_FIELDS = (
    "race_event_id,driver_id,stint_index,compound,"
    "lap_window_start,lap_window_end,stint_length,"
    "degradation_slope,clean_air_pace,traffic_share,gap_to_car_ahead,pit_ended,"
    "race_events(circuit_id)"
)


def get_all_stints(client: Any = None, page_size: int = 1000) -> list[dict[str, Any]]:
    """All driver_race_stints, paginated. Used to train the degradation model."""
    client = client or get_client()
    rows: list[dict[str, Any]] = []
    start = 0
    while True:
        batch = (
            client.table("driver_race_stints")
            .select(_STINT_FIELDS)
            .range(start, start + page_size - 1)
            .execute()
            .data
            or []
        )
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def get_stints_for_circuit(circuit_id: int, client: Any = None) -> list[dict[str, Any]]:
    """Historical stints run at a given circuit (track-specific degradation prior)."""
    client = client or get_client()
    result = (
        client.table("driver_race_stints")
        .select(_STINT_FIELDS)
        .eq("race_events.circuit_id", circuit_id)
        .execute()
    )
    # The embedded filter on race_events keeps only rows whose race is at this
    # circuit; rows with a null embed are dropped defensively.
    return [row for row in (result.data or []) if row.get("race_events")]


# ── Weekend entries (stage-specific inputs) ─────────────────────────────────

_ENTRY_FIELDS = (
    "qualifying_final_grid_pos,qualifying_pos,"
    "fp1_pos,fp2_pos,fp3_pos,"
    "driver_avg_pace,driver_clean_air_pace,driver_grid_avg_pace,"
    "driver_pace_score_0_100,"
    "drivers(driver_code,full_name),teams(team_name)"
)


def get_race_entries(race_event_id: int, client: Any = None) -> list[dict[str, Any]]:
    """
    driver_race_entries for this race. The presence of practice / qualifying /
    pace columns is what lets the simulator detect how much weekend data exists
    for the requested report stage.
    """
    client = client or get_client()
    result = (
        client.table("driver_race_entries")
        .select(_ENTRY_FIELDS)
        .eq("race_id", race_event_id)
        .execute()
    )
    flattened: list[dict[str, Any]] = []
    for row in result.data or []:
        driver = row.get("drivers") or {}
        team = row.get("teams") or {}
        flat = {k: v for k, v in row.items() if k not in {"drivers", "teams"}}
        flat["driver_code"] = driver.get("driver_code")
        flat["full_name"] = driver.get("full_name")
        flat["team_name"] = team.get("team_name")
        flattened.append(flat)
    return flattened


# ── strategy_reports cache ──────────────────────────────────────────────────

def get_cached_report(
    race_event_id: int,
    report_stage: str,
    client: Any = None,
) -> Optional[dict[str, Any]]:
    client = client or get_client()
    result = (
        client.table("strategy_reports")
        .select("*")
        .eq("race_event_id", race_event_id)
        .eq("report_stage", report_stage)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def upsert_report(row: dict[str, Any], client: Any = None) -> Optional[dict[str, Any]]:
    """Upsert a strategy_reports row, keyed by (race_event_id, report_stage)."""
    client = client or get_client()
    result = (
        client.table("strategy_reports")
        .upsert(row, on_conflict="race_event_id,report_stage")
        .execute()
    )
    return result.data[0] if result.data else None


# ── Input hashing (mirrors ai_insights._hash_payload) ───────────────────────

def hash_inputs(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

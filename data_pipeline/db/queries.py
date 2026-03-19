from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from .supabase_client import get_client

AEST = timezone(timedelta(hours=10))


# ---------------------------------------------------------------------------
# Pending-session detection
# ---------------------------------------------------------------------------

def get_pending_sessions() -> list[dict]:
    """Find sessions that ended >2 h ago but haven't been fetched."""
    client = get_client()
    cutoff = datetime.now(AEST) - timedelta(hours=2)
    result = client.rpc(
        "get_pending_sessions", {"cutoff": cutoff.isoformat()}
    ).execute()
    return result.data


def mark_session_fetched(session_id: int) -> None:
    """Mark a session as successfully fetched."""
    client = get_client()
    (
        client.table("race_sessions")
        .update({"data_fetched": True})
        .eq("id", session_id)
        .execute()
    )


# ---------------------------------------------------------------------------
# FK resolution helpers
# ---------------------------------------------------------------------------

def resolve_race_id(season: int, round_num: int) -> Optional[str]:
    """Look up ``races.id`` (UUID) for a given season + round."""
    client = get_client()
    result = (
        client.table("races")
        .select("id")
        .eq("season", season)
        .eq("round", round_num)
        .limit(1)
        .execute()
    )
    return result.data[0]["id"] if result.data else None


def resolve_driver_id(driver_code: str) -> Optional[str]:
    """Look up ``drivers.id`` (UUID) for a driver code."""
    client = get_client()
    result = (
        client.table("drivers")
        .select("id")
        .eq("driver_code", driver_code)
        .limit(1)
        .execute()
    )
    return result.data[0]["id"] if result.data else None


def resolve_team_id(team_name: str, season: int) -> Optional[str]:
    """Look up ``teams.id`` (UUID) for a team name + season."""
    client = get_client()
    result = (
        client.table("teams")
        .select("id")
        .eq("team_name", team_name)
        .eq("season", season)
        .limit(1)
        .execute()
    )
    return result.data[0]["id"] if result.data else None


# ---------------------------------------------------------------------------
# Upserts
# ---------------------------------------------------------------------------

def upsert_driver_race_entry(entry: dict) -> Optional[dict]:
    """Upsert a ``driver_race_entries`` row and return the resulting row."""
    client = get_client()
    result = (
        client.table("driver_race_entries")
        .upsert(entry, on_conflict="race_id,driver_id")
        .execute()
    )
    return result.data[0] if result.data else None


def upsert_laps(laps: list[dict]) -> None:
    """Upsert lap rows in bulk."""
    client = get_client()
    (
        client.table("laps")
        .upsert(laps, on_conflict="driver_race_entry_id,lap_number")
        .execute()
    )

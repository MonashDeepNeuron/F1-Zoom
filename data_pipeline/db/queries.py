from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from .supabase_client import get_client


TEAM_NAME_ALIASES = {
    "Haas F1 Team": "Haas",
    "Oracle Red Bull Racing": "Red Bull Racing",
    "Red Bull": "Red Bull Racing",
    "RB": "Racing Bulls",
    "RB F1 Team": "Racing Bulls",
    "Visa Cash App RB": "Racing Bulls",
    "Visa Cash App Racing Bulls F1 Team": "Racing Bulls",
    "Kick Sauber": "Audi",
    "Stake F1 Team Kick Sauber": "Audi",
    "Sauber": "Audi",
    "Aston Martin Aramco": "Aston Martin",
    "Aston Martin Aramco Mercedes": "Aston Martin",
}


# ---------------------------------------------------------------------------
# Pending-session detection
# ---------------------------------------------------------------------------

def get_pending_sessions() -> list[dict]:
    """Find sessions that ended >2 h ago but haven't been fetched."""
    client = get_client()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
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

def resolve_race_id(season: int, round_num: int) -> Optional[int]:
    """Look up ``race_events.id`` for a given season + round."""
    client = get_client()
    result = (
        client.table("race_events")
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
    if not team_name:
        return None

    client = get_client()

    candidates = [team_name]
    alias = TEAM_NAME_ALIASES.get(team_name)
    if alias and alias not in candidates:
        candidates.append(alias)

    for candidate in candidates:
        result = (
            client.table("teams")
            .select("id")
            .eq("team_name", candidate)
            .eq("season", season)
            .limit(1)
            .execute()
        )
        if result.data:
            return result.data[0]["id"]

    return None


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


def get_recent_finish_positions(
    driver_ids: list[str],
    current_season: int,
    current_round: int,
) -> dict[str, list[float]]:
    """
    Return prior race finish positions for the supplied drivers, newest first.

    The current race is excluded by filtering to rows strictly before the given
    ``(season, round)``.
    """
    if not driver_ids:
        return {}

    client = get_client()
    result = (
        client.table("driver_race_entries")
        .select("driver_id, race_finish_pos, race_events(season, round)")
        .in_("driver_id", driver_ids)
        .execute()
    )

    by_driver: dict[str, list[tuple[int, int, float]]] = {
        driver_id: [] for driver_id in driver_ids
    }
    for row in result.data or []:
        finish_pos = row.get("race_finish_pos")
        race_event = row.get("race_events") or {}
        season = race_event.get("season")
        round_num = race_event.get("round")
        driver_id = row.get("driver_id")

        if (
            driver_id not in by_driver
            or finish_pos is None
            or season is None
            or round_num is None
        ):
            continue

        if (season, round_num) >= (current_season, current_round):
            continue

        by_driver[driver_id].append((int(season), int(round_num), float(finish_pos)))

    history: dict[str, list[float]] = {}
    for driver_id, rows in by_driver.items():
        rows.sort(key=lambda item: (item[0], item[1]), reverse=True)
        history[driver_id] = [finish for _, _, finish in rows]

    return history

def get_circuit_turn_count(circuit_name: str) -> Optional[int]:
    """Look up the number of turns for a circuit by name."""
    try:
        client = get_client()
        result = (
            client.table("circuits")
            .select("corners")
            .ilike("file_slug", circuit_name)
            .limit(1)
            .execute()
        )
        return result.data[0]["corners"] if result.data else None
    except Exception as e:
        print(f"Error fetching turn count for circuit '{circuit_name}': {e}")
        return None
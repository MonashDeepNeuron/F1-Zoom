"""
Orchestrator — the pipeline brain.

Queries Supabase for sessions that ended >2 h ago but haven't been fetched,
fetches data from FastF1, upserts to Supabase, and marks sessions as done.

Run from the project root:
    python -m data_pipeline.orchestrator
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache

import numpy as np
import pandas as pd

from data_pipeline.db.queries import (
    get_pending_sessions,
    mark_session_fetched,
    resolve_driver_id,
    resolve_race_id,
    resolve_team_id,
    upsert_driver_race_entry,
    upsert_laps,
)
from data_pipeline.fetchers.session_fetcher import (
    fetch_lap_data,
    fetch_qualifying_times,
    fetch_race_results,
    fetch_session_results,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(name)s  %(levelname)s  %(message)s",
)
log = logging.getLogger("orchestrator")

PRACTICE_PREFIX = {
    "practice_1": "fp1",
    "practice_2": "fp2",
    "practice_3": "fp3",
}


# ---------------------------------------------------------------------------
# FK resolution — cached for the lifetime of a single pipeline run so we
# don't round-trip to Supabase for every driver × session combination.
# ---------------------------------------------------------------------------

@lru_cache(maxsize=64)
def _race_id(season: int, round_num: int):
    return resolve_race_id(season, round_num)


@lru_cache(maxsize=128)
def _driver_id(driver_code: str):
    return resolve_driver_id(driver_code)


@lru_cache(maxsize=64)
def _team_id(team_name: str, season: int):
    return resolve_team_id(team_name, season)


# ---------------------------------------------------------------------------
# Value cleaning — pandas / numpy types → JSON-safe Python natives
# ---------------------------------------------------------------------------

def _clean(val):
    if val is None:
        return None
    if isinstance(val, float) and (pd.isna(val) or np.isnan(val)):
        return None
    if hasattr(val, "item"):
        return val.item()
    return val


def _base_entry(driver_code: str, team: str, season: int, round_num: int) -> dict:
    """Return the FK columns common to every driver_race_entries upsert."""
    return {
        "race_id": _race_id(season, round_num),
        "driver_id": _driver_id(driver_code),
        "team_id": _team_id(team, season),
    }


# ---------------------------------------------------------------------------
# Session handlers — one per logical session group
# ---------------------------------------------------------------------------

def _process_practice(session: dict) -> None:
    """FP1 / FP2 / FP3 → upsert fpN_pos + fpN_time_fastest_lap."""
    prefix = PRACTICE_PREFIX[session["session_type"]]
    results_df = fetch_session_results(
        session["season"], session["grand_prix_name"], session["session_type"],
    )

    upserted = 0
    for _, row in results_df.iterrows():
        entry = _base_entry(
            row["driver_code"], row["team"],
            session["season"], session["round"],
        )
        if not entry["race_id"] or not entry["driver_id"]:
            continue
        entry[f"{prefix}_pos"] = _clean(row.get("position"))
        entry[f"{prefix}_time_fastest_lap"] = _clean(row.get("fastest_lap"))
        upsert_driver_race_entry(entry)
        upserted += 1

    log.info("Upserted %d practice entries (%s)", upserted, prefix)


def _process_qualifying(session: dict) -> None:
    """Qualifying → upsert Q1/Q2/Q3 times, positions, and grid pos."""
    qual_df = fetch_qualifying_times(
        session["season"], session["grand_prix_name"],
    )

    upserted = 0
    for _, row in qual_df.iterrows():
        entry = _base_entry(
            row["driver_code"], row["team"],
            session["season"], session["round"],
        )
        if not entry["race_id"] or not entry["driver_id"]:
            continue

        for col in row.index:
            if col in ("driver_code", "team"):
                continue
            cleaned = _clean(row[col])
            if cleaned is not None:
                entry[col] = cleaned

        entry.setdefault(
            "qualifying_pos", entry.get("qualifying_final_grid_pos"),
        )

        upsert_driver_race_entry(entry)
        upserted += 1

    log.info("Upserted %d qualifying entries", upserted)


def _process_sprint_qualifying(session: dict) -> None:
    """Sprint Qualifying → upsert basic grid position."""
    results_df = fetch_session_results(
        session["season"], session["grand_prix_name"], session["session_type"],
    )

    upserted = 0
    for _, row in results_df.iterrows():
        entry = _base_entry(
            row["driver_code"], row["team"],
            session["season"], session["round"],
        )
        if not entry["race_id"] or not entry["driver_id"]:
            continue
        entry["sprint_qualifying_final_grid_pos"] = _clean(row.get("position"))
        upsert_driver_race_entry(entry)
        upserted += 1

    log.info("Upserted %d sprint-qualifying entries", upserted)


def _process_race(session: dict) -> None:
    """Race → upsert race results + detailed lap data."""
    season = session["season"]
    gp_name = session["grand_prix_name"]

    race_df = fetch_race_results(season, gp_name)

    entry_id_map: dict[str, str] = {}
    for _, row in race_df.iterrows():
        entry = _base_entry(
            row["driver_code"], row["team"], season, session["round"],
        )
        if not entry["race_id"] or not entry["driver_id"]:
            continue

        for col in row.index:
            if col in ("driver_code", "team"):
                continue
            cleaned = _clean(row[col])
            if cleaned is not None:
                entry[col] = cleaned

        result = upsert_driver_race_entry(entry)
        if result:
            entry_id_map[row["driver_code"]] = result["id"]

    log.info("Upserted %d race entries", len(entry_id_map))

    # Lap-by-lap data
    laps_df = fetch_lap_data(season, gp_name)
    if laps_df.empty or not entry_id_map:
        return

    lap_rows = []
    for _, lap in laps_df.iterrows():
        dre_id = entry_id_map.get(lap["driver_code"])
        if dre_id is None:
            continue
        lap_rows.append({
            "driver_race_entry_id": dre_id,
            "lap_number": int(lap["lap_number"]),
            "lap_time": _clean(lap["lap_time"]),
            "compound": _clean(lap.get("compound")),
            "track_status": _clean(lap.get("track_status")),
            "stint_index": int(lap.get("stint_index", 0)),
        })

    if lap_rows:
        upsert_laps(lap_rows)
        log.info("Upserted %d laps", len(lap_rows))


def _process_sprint(session: dict) -> None:
    """Sprint race → upsert sprint finish position + fastest lap."""
    results_df = fetch_session_results(
        session["season"], session["grand_prix_name"], session["session_type"],
    )

    upserted = 0
    for _, row in results_df.iterrows():
        entry = _base_entry(
            row["driver_code"], row["team"],
            session["season"], session["round"],
        )
        if not entry["race_id"] or not entry["driver_id"]:
            continue
        entry["sprint_finish_pos"] = _clean(row.get("position"))
        entry["sprint_fastest_lap"] = _clean(row.get("fastest_lap"))
        upsert_driver_race_entry(entry)
        upserted += 1

    log.info("Upserted %d sprint entries", upserted)


# ---------------------------------------------------------------------------
# Top-level dispatch
# ---------------------------------------------------------------------------

_HANDLERS = {
    "practice_1": _process_practice,
    "practice_2": _process_practice,
    "practice_3": _process_practice,
    "qualifying": _process_qualifying,
    "sprint_qualifying": _process_sprint_qualifying,
    "race": _process_race,
    "sprint": _process_sprint,
}


MAX_RETRIES = 3
RETRY_BACKOFF_SECONDS = 30


def process_session(session: dict) -> None:
    """Dispatch a single pending session to the appropriate handler."""
    session_type = session["session_type"]
    season = session["season"]
    gp_name = session["grand_prix_name"]
    session_id = session["session_id"]

    log.info("Processing %d %s %s …", season, gp_name, session_type)

    handler = _HANDLERS.get(session_type)
    if handler is None:
        log.warning("Unknown session type %r — skipping", session_type)
        return

    handler(session)

    mark_session_fetched(session_id)
    log.info("Done: %d %s %s", season, gp_name, session_type)


def _process_with_retry(session: dict) -> None:
    """Try processing a session up to MAX_RETRIES times with backoff."""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            process_session(session)
            return
        except Exception:
            if attempt == MAX_RETRIES:
                log.exception(
                    "Failed session %s after %d attempts — giving up",
                    session, MAX_RETRIES,
                )
            else:
                wait = RETRY_BACKOFF_SECONDS * attempt
                log.warning(
                    "Attempt %d/%d failed for %s %s %s — retrying in %ds",
                    attempt, MAX_RETRIES,
                    session.get("season"), session.get("grand_prix_name"),
                    session.get("session_type"), wait,
                    exc_info=True,
                )
                time.sleep(wait)


def main() -> None:
    pending = get_pending_sessions()

    if not pending:
        log.info("No pending sessions to process.")
        return

    log.info("Found %d pending session(s)", len(pending))

    succeeded, failed = 0, 0
    for session in pending:
        try:
            _process_with_retry(session)
            succeeded += 1
        except Exception:
            failed += 1

    log.info("Pipeline complete: %d succeeded, %d failed", succeeded, failed)


if __name__ == "__main__":
    main()

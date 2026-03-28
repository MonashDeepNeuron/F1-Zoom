"""
FastF1 session fetcher — the core of the data pipeline.

Each public function takes (season, gp_name) and returns a DataFrame
whose column names align with the Supabase schema, ready for upsert.

Transformation logic is extracted from:
  - qualifying_to_race_performance.py  (FP/Q positions, Q1-Q3 times)
  - car_lap_metrics.py                 (per-lap data with track status)
  - car_race_summary.py                (race result aggregation)
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import fastf1
import numpy as np
import pandas as pd

from data_pipeline.config.driver_config import (
    get_team_from_driver,
    is_sprint_weekend,
)

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(__file__).resolve().parents[2] / "cache"
_CACHE_DIR.mkdir(exist_ok=True)
fastf1.Cache.enable_cache(str(_CACHE_DIR))

SESSION_TYPE_MAP = {
    "practice_1": "FP1",
    "practice_2": "FP2",
    "practice_3": "FP3",
    "qualifying": "Q",
    "sprint_qualifying": "SQ",
    "sprint": "S",
    "race": "R",
}

TRACK_STATUS_LABELS = {
    "1": "Green Flag",
    "2": "Yellow Flag",
    "3": "Safety Car Ending",
    "4": "Safety Car",
    "5": "Red Flag",
    "6": "Virtual Safety Car Deployed",
    "7": "Virtual Safety Car Ending",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_session(season: int, gp_name: str, session_type: str):
    """Load and return a FastF1 session object."""
    ff1_key = SESSION_TYPE_MAP.get(session_type, session_type)
    session = fastf1.get_session(season, gp_name, ff1_key)
    session.load()
    return session


def _get_round_number(season: int, gp_name: str) -> int:
    """Resolve the calendar round number for a GP via FastF1 schedule."""
    try:
        schedule = fastf1.get_event_schedule(season)
        match = schedule[schedule["EventName"] == gp_name]
        if not match.empty:
            return int(match.iloc[0]["RoundNumber"])
    except Exception:
        pass
    return 1


def _format_lap_time(td) -> Optional[str]:
    """Format a Timedelta as ``M:SS.mmm``, or *None* if NaN."""
    if td is None or pd.isna(td):
        return None
    total = td.total_seconds()
    m, rem = divmod(total, 60)
    s = int(rem)
    ms = int((rem % 1) * 1000)
    return f"{int(m)}:{s:02d}.{ms:03d}"


def _td_to_seconds(td) -> Optional[float]:
    """Convert a Timedelta to total seconds, or *None* if NaN."""
    if td is None or pd.isna(td):
        return None
    return td.total_seconds()


def _select_valid_race_laps(driver_laps: pd.DataFrame) -> pd.DataFrame:
    """
    Keep the laps that are most useful for driver-level race metrics.

    This intentionally errs on the side of filling data rather than leaving
    columns empty: we exclude obviously invalid / in-out laps, but otherwise
    keep accurate timed laps even if the race had interruptions.
    """
    if driver_laps.empty:
        return driver_laps

    valid = driver_laps.copy()
    if "LapTime" in valid.columns:
        valid = valid[valid["LapTime"].notna()]
    if "IsAccurate" in valid.columns:
        valid = valid[valid["IsAccurate"] != False]  # noqa: E712
    if "PitOutTime" in valid.columns:
        valid = valid[valid["PitOutTime"].isna()]
    if "PitInTime" in valid.columns:
        valid = valid[valid["PitInTime"].isna()]
    return valid


def _extract_q_round(results: pd.DataFrame, q_col: str):
    """
    For a qualifying round column (``Q1`` / ``Q2`` / ``Q3``), return two dicts:
    ``(position_dict, seconds_dict)`` keyed by driver abbreviation.
    """
    subset = results[["Abbreviation", q_col]].dropna(subset=[q_col]).copy()
    subset["_sec"] = subset[q_col].apply(_td_to_seconds)
    subset = subset.sort_values("_sec")
    pos_dict = {
        row["Abbreviation"]: pos
        for pos, (_, row) in enumerate(subset.iterrows(), start=1)
    }
    sec_dict = dict(zip(subset["Abbreviation"], subset["_sec"]))
    return pos_dict, sec_dict


def _estimate_corner_speed(session, driver_code: str, lap_numbers: list[int]) -> Optional[float]:
    """
    Estimate a driver's corner speed from telemetry on a small sample of laps.

    We use the minimum speed below ~150 km/h on each sampled lap as a proxy for
    slow-corner speed, then average those minima.
    """
    if not lap_numbers:
        return None

    driver_laps = session.laps.pick_driver(driver_code)
    if driver_laps.empty:
        return None

    corner_mins: list[float] = []
    for lap_number in lap_numbers[:5]:
        lap = driver_laps[driver_laps["LapNumber"] == lap_number]
        if lap.empty:
            continue
        try:
            telemetry = lap.iloc[0].get_telemetry()
        except Exception:
            continue
        if telemetry is None or telemetry.empty or "Speed" not in telemetry.columns:
            continue

        corner_speeds = telemetry["Speed"][telemetry["Speed"] < 150]
        if len(corner_speeds) > 0:
            corner_mins.append(float(corner_speeds.min()))

    if not corner_mins:
        return None
    return float(np.mean(corner_mins))


def _resolve_track_status(session, lap_time_utc: pd.Timestamp) -> str:
    """
    Map a UTC lap timestamp to a human-readable track status string by
    scanning the session's ``track_status`` timeline.
    """
    ts_df = session.track_status
    if ts_df is None or ts_df.empty:
        return "Green Flag"
    if "Time" not in ts_df.columns or "Status" not in ts_df.columns:
        return "Green Flag"

    session_start = session.date
    if session_start.tz is None:
        session_start = session_start.tz_localize("UTC")
    else:
        session_start = session_start.tz_convert("UTC")

    if lap_time_utc.tz is None:
        lap_time_utc = lap_time_utc.tz_localize("UTC")
    else:
        lap_time_utc = lap_time_utc.tz_convert("UTC")

    ts_stamps = session_start + ts_df["Time"]
    mask = ts_stamps <= lap_time_utc
    if not mask.any():
        return "Green Flag"

    code = str(ts_df[mask].iloc[-1]["Status"])
    return TRACK_STATUS_LABELS.get(code, "Unknown")


# ---------------------------------------------------------------------------
# Public fetch functions
# ---------------------------------------------------------------------------

def fetch_session_results(
    season: int,
    gp_name: str,
    session_type: str,
) -> pd.DataFrame:
    """
    Generic result fetcher for *any* session type.

    Returns a DataFrame with columns:
        driver_code, team, position, fastest_lap, status
    """
    session = _load_session(season, gp_name, session_type)
    results = session.results

    rows = []
    for _, row in results.iterrows():
        dc = row["Abbreviation"]
        driv_laps = session.laps.pick_driver(dc)
        fl = driv_laps["LapTime"].min() if len(driv_laps) > 0 else None

        rows.append({
            "driver_code": dc,
            "team": row["TeamName"],
            "position": int(row["Position"]) if pd.notna(row["Position"]) else None,
            "fastest_lap": _format_lap_time(fl),
            "status": row.get("Status") if pd.notna(row.get("Status")) else None,
        })

    logger.info(
        "fetch_session_results  %s %s %s  → %d drivers",
        season, gp_name, session_type, len(rows),
    )
    return pd.DataFrame(rows)


def fetch_practice_results(season: int, gp_name: str) -> pd.DataFrame:
    """
    Fetch free-practice quicklap rankings.

    Sprint weekends only have FP1; standard weekends have FP1-FP3.
    Returns one row per driver with columns:
        driver_code, team,
        fp1_pos, fp1_time_fastest_lap,
        fp2_pos, fp2_time_fastest_lap,
        fp3_pos, fp3_time_fastest_lap
    """
    sprint = is_sprint_weekend(gp_name, season)
    round_num = _get_round_number(season, gp_name)

    fp_sessions = ["practice_1"]
    if not sprint:
        fp_sessions += ["practice_2", "practice_3"]

    driver_map: dict[str, dict] = {}

    for stype in fp_sessions:
        prefix = stype.replace("practice_", "fp")
        session = _load_session(season, gp_name, stype)
        quicklaps = session.laps.pick_quicklaps()

        if quicklaps.empty:
            logger.warning("No quicklaps for %s %s %s", season, gp_name, stype)
            continue

        fastest = quicklaps.groupby("Driver")["LapTime"].min().sort_values()
        positions = {
            drv: pos for pos, (drv, _) in enumerate(fastest.items(), start=1)
        }
        times = fastest.to_dict()

        for dc in quicklaps["Driver"].unique():
            if dc not in driver_map:
                driver_map[dc] = {
                    "driver_code": dc,
                    "team": get_team_from_driver(dc, season, round_num),
                }
            driver_map[dc][f"{prefix}_pos"] = positions.get(dc)
            driver_map[dc][f"{prefix}_time_fastest_lap"] = _format_lap_time(
                times.get(dc)
            )

    df = pd.DataFrame(driver_map.values())
    logger.info(
        "fetch_practice_results  %s %s  → %d drivers", season, gp_name, len(df),
    )
    return df


def fetch_qualifying_times(season: int, gp_name: str) -> pd.DataFrame:
    """
    Fetch Q1/Q2/Q3 (and SQ1/SQ2/SQ3 on sprint weekends).

    Returns one row per driver with columns:
        driver_code, team,
        qualifying_final_grid_pos,
        q1_time_seconds, q1_position, q1_fastest_lap,
        q2_time_seconds, q2_position, q2_fastest_lap,
        q3_time_seconds, q3_position, q3_fastest_lap,
        (sprint only) sprint_qualifying_final_grid_pos,
        sq1_time_seconds, sq1_position, sq1_fastest_lap, …
    """
    sprint = is_sprint_weekend(gp_name, season)

    q_session = _load_session(season, gp_name, "qualifying")
    q_results = q_session.results.sort_values("Position").reset_index(drop=True)

    q1_pos, q1_sec = _extract_q_round(q_results, "Q1")
    q2_pos, q2_sec = _extract_q_round(q_results, "Q2")
    q3_pos, q3_sec = _extract_q_round(q_results, "Q3")

    sq_lookup: dict[str, dict] = {}
    if sprint:
        sq_session = _load_session(season, gp_name, "sprint_qualifying")
        sq_results = sq_session.results
        sq1_pos, sq1_sec = _extract_q_round(sq_results, "Q1")
        sq2_pos, sq2_sec = _extract_q_round(sq_results, "Q2")
        sq3_pos, sq3_sec = _extract_q_round(sq_results, "Q3")

        for _, row in sq_results.iterrows():
            dc = row["Abbreviation"]
            sq_lookup[dc] = {
                "sprint_qualifying_final_grid_pos": (
                    int(row["Position"]) if pd.notna(row["Position"]) else None
                ),
                "sq1_time_seconds": sq1_sec.get(dc),
                "sq1_position": sq1_pos.get(dc),
                "sq1_fastest_lap": _format_lap_time(row.get("Q1")),
                "sq2_time_seconds": sq2_sec.get(dc),
                "sq2_position": sq2_pos.get(dc),
                "sq2_fastest_lap": _format_lap_time(row.get("Q2")),
                "sq3_time_seconds": sq3_sec.get(dc),
                "sq3_position": sq3_pos.get(dc),
                "sq3_fastest_lap": _format_lap_time(row.get("Q3")),
            }

    rows = []
    for _, row in q_results.iterrows():
        dc = row["Abbreviation"]
        entry = {
            "driver_code": dc,
            "team": row["TeamName"],
            "qualifying_final_grid_pos": (
                int(row["Position"]) if pd.notna(row["Position"]) else None
            ),
            "q1_time_seconds": q1_sec.get(dc),
            "q1_position": q1_pos.get(dc),
            "q1_fastest_lap": _format_lap_time(row.get("Q1")),
            "q2_time_seconds": q2_sec.get(dc),
            "q2_position": q2_pos.get(dc),
            "q2_fastest_lap": _format_lap_time(row.get("Q2")),
            "q3_time_seconds": q3_sec.get(dc),
            "q3_position": q3_pos.get(dc),
            "q3_fastest_lap": _format_lap_time(row.get("Q3")),
        }
        if sprint:
            entry.update(sq_lookup.get(dc, {}))
        rows.append(entry)

    df = pd.DataFrame(rows)
    logger.info(
        "fetch_qualifying_times  %s %s  → %d drivers", season, gp_name, len(df),
    )
    return df


def fetch_race_results(season: int, gp_name: str) -> pd.DataFrame:
    """
    Fetch race finishing positions, status, and fastest lap.
    On sprint weekends also returns sprint_finish_pos / sprint_fastest_lap.

    Returns one row per driver with columns:
        driver_code, team,
        race_finish_pos, race_status, fastest_lap,
        (sprint only) sprint_finish_pos, sprint_fastest_lap
    """
    sprint = is_sprint_weekend(gp_name, season)

    race_session = _load_session(season, gp_name, "race")
    race_results = race_session.results

    sprint_data: dict[str, dict] = {}
    if sprint:
        sprint_session = _load_session(season, gp_name, "sprint")
        sprint_results = sprint_session.results
        for _, row in sprint_results.iterrows():
            dc = row["Abbreviation"]
            driv_laps = sprint_session.laps.pick_driver(dc)
            fl = driv_laps["LapTime"].min() if len(driv_laps) > 0 else None
            sprint_data[dc] = {
                "sprint_finish_pos": (
                    int(row["Position"]) if pd.notna(row["Position"]) else None
                ),
                "sprint_fastest_lap": _format_lap_time(fl),
            }

    rows = []
    for _, row in race_results.iterrows():
        dc = row["Abbreviation"]
        driv_laps = race_session.laps.pick_driver(dc)
        fl = driv_laps["LapTime"].min() if len(driv_laps) > 0 else None

        entry = {
            "driver_code": dc,
            "team": row["TeamName"],
            "race_finish_pos": (
                int(row["Position"]) if pd.notna(row["Position"]) else None
            ),
            "race_status": row.get("Status") if pd.notna(row.get("Status")) else None,
            "fastest_lap": _format_lap_time(fl),
        }
        if sprint:
            entry.update(sprint_data.get(dc, {}))
        rows.append(entry)

    df = pd.DataFrame(rows)
    logger.info(
        "fetch_race_results  %s %s  → %d drivers", season, gp_name, len(df),
    )
    return df


def fetch_race_analysis_metrics(season: int, gp_name: str) -> pd.DataFrame:
    """
    Derive driver-level race metrics directly from FastF1.

    This fills the analysis-oriented columns in ``driver_race_entries`` that
    would otherwise stay null after a race fetch.
    """
    session = _load_session(season, gp_name, "race")
    laps = session.laps

    if laps.empty:
        logger.warning("No race laps for %s %s analysis metrics", season, gp_name)
        return pd.DataFrame()

    rows = []
    for driver_code in sorted(laps["Driver"].dropna().unique()):
        driver_laps = _select_valid_race_laps(laps.pick_driver(driver_code))
        if driver_laps.empty:
            rows.append({"driver_code": driver_code})
            continue

        lap_seconds = driver_laps["LapTime"].apply(_td_to_seconds).dropna()
        avg_pace = float(lap_seconds.mean()) if len(lap_seconds) > 0 else None

        clean_air_pace = None
        if "DriverAhead" in driver_laps.columns:
            clean_laps = driver_laps[
                driver_laps["DriverAhead"].isna()
                | (driver_laps["DriverAhead"].astype(str).str.strip() == "")
            ]
            clean_lap_seconds = clean_laps["LapTime"].apply(_td_to_seconds).dropna()
            if len(clean_lap_seconds) > 0:
                clean_air_pace = float(clean_lap_seconds.mean())

        top_speed = None
        if "SpeedST" in driver_laps.columns:
            speed_trap = pd.to_numeric(driver_laps["SpeedST"], errors="coerce").dropna()
            if len(speed_trap) > 0:
                top_speed = float(speed_trap.max())

        lap_numbers = (
            pd.to_numeric(driver_laps["LapNumber"], errors="coerce")
            .dropna()
            .sort_values()
            .astype(int)
            .tolist()
        )
        corner_speed = _estimate_corner_speed(session, driver_code, lap_numbers)

        rows.append({
            "driver_code": driver_code,
            "driver_avg_pace": avg_pace,
            "driver_clean_air_pace": clean_air_pace,
            "driver_top_speed": top_speed,
            "driver_corner_speed": corner_speed,
        })

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    avg_pace_series = pd.to_numeric(df.get("driver_avg_pace"), errors="coerce")
    grid_avg_pace = float(avg_pace_series.mean()) if avg_pace_series.notna().any() else None
    grid_std_pace = float(avg_pace_series.std()) if avg_pace_series.notna().sum() > 1 else None

    df["driver_grid_avg_pace"] = grid_avg_pace
    df["driver_pace_delta_to_grid"] = avg_pace_series - grid_avg_pace if grid_avg_pace is not None else np.nan

    if grid_std_pace and not np.isnan(grid_std_pace) and grid_std_pace > 0:
        df["driver_pace_zscore_vs_grid"] = df["driver_pace_delta_to_grid"] / grid_std_pace
        df["driver_pace_score_vs_grid"] = -df["driver_pace_zscore_vs_grid"]
    else:
        df["driver_pace_zscore_vs_grid"] = np.nan
        df["driver_pace_score_vs_grid"] = np.nan

    if avg_pace_series.notna().any():
        df["driver_pace_score_0_100"] = 100 * (
            1 - avg_pace_series.rank(pct=True, ascending=True)
        )
    else:
        df["driver_pace_score_0_100"] = np.nan

    top_speed_series = pd.to_numeric(df.get("driver_top_speed"), errors="coerce")
    corner_speed_series = pd.to_numeric(df.get("driver_corner_speed"), errors="coerce")
    df["driver_top_speed_rank"] = top_speed_series.rank(ascending=False, method="min")
    df["driver_corner_speed_rank"] = corner_speed_series.rank(ascending=False, method="min")
    df["driver_drag_index"] = (
        df["driver_top_speed_rank"] - df["driver_corner_speed_rank"]
    )

    logger.info(
        "fetch_race_analysis_metrics  %s %s  → %d drivers",
        season, gp_name, len(df),
    )
    return df


def fetch_lap_data(season: int, gp_name: str) -> pd.DataFrame:
    """
    Fetch lap-by-lap telemetry for the race session.

    Returns one row per driver per lap with columns matching the
    Supabase ``laps`` table:
        driver_code, lap_number, lap_time, compound,
        track_status, stint_index
    """
    session = _load_session(season, gp_name, "race")
    laps = session.laps

    if laps.empty:
        logger.warning("No lap data for %s %s", season, gp_name)
        return pd.DataFrame()

    records = []
    for _, lap in laps.iterrows():
        lt = lap.get("LapTime")
        if lt is None or pd.isna(lt):
            continue

        lap_start = lap.get("LapStartDate")
        if lap_start is not None and not pd.isna(lap_start):
            track_status = _resolve_track_status(session, lap_start)
        else:
            track_status = "Green Flag"

        records.append({
            "driver_code": lap["Driver"],
            "lap_number": int(lap["LapNumber"]),
            "lap_time": lt.total_seconds(),
            "compound": lap.get("Compound"),
            "track_status": track_status,
            "stint_index": int(lap.get("Stint", 0)),
        })

    df = pd.DataFrame(records)
    logger.info(
        "fetch_lap_data  %s %s  → %d laps across %d drivers",
        season, gp_name, len(df),
        df["driver_code"].nunique() if not df.empty else 0,
    )
    return df


def fetch_full_weekend(season: int, gp_name: str) -> pd.DataFrame:
    """
    Orchestrate all fetchers and merge into a single DataFrame with
    one row per driver — matching the ``driver_race_entries`` schema.

    Columns include practice positions, qualifying times, race results,
    and best-effort derived race metrics from FastF1.
    """
    logger.info("fetch_full_weekend  %s %s  — starting", season, gp_name)

    practice_df = fetch_practice_results(season, gp_name)
    qualifying_df = fetch_qualifying_times(season, gp_name)
    race_df = fetch_race_results(season, gp_name)
    analysis_df = fetch_race_analysis_metrics(season, gp_name)

    merged = practice_df.copy()

    if not qualifying_df.empty:
        qual_cols = qualifying_df.drop(columns=["team"], errors="ignore")
        merged = merged.merge(qual_cols, on="driver_code", how="outer")

    if not race_df.empty:
        race_cols = race_df.drop(columns=["team"], errors="ignore")
        merged = merged.merge(race_cols, on="driver_code", how="outer")

    if not analysis_df.empty:
        merged = merged.merge(analysis_df, on="driver_code", how="outer")

    # Back-fill team from qualifying/race if practice didn't cover a driver
    if merged["team"].isna().any():
        team_lookup = {}
        for src in [qualifying_df, race_df]:
            if "team" in src.columns:
                team_lookup.update(
                    src.set_index("driver_code")["team"].dropna().to_dict()
                )
        merged["team"] = merged["team"].fillna(merged["driver_code"].map(team_lookup))

    merged["qualifying_pos"] = pd.to_numeric(
        merged.get("qualifying_final_grid_pos"), errors="coerce"
    )
    merged["position_gain_from_quali_to_race"] = (
        merged["qualifying_pos"]
        - pd.to_numeric(merged.get("race_finish_pos"), errors="coerce")
    )

    merged = merged.loc[:, ~merged.columns.duplicated()]

    logger.info(
        "fetch_full_weekend  %s %s  → %d drivers, %d columns",
        season, gp_name, len(merged), len(merged.columns),
    )
    return merged

"""
ETL: derive driver_race_stints and track_strategy_profiles from the local CSV
dump and upsert them into the live Supabase tables.

Why CSV, not the live `laps` table: the deployed `laps` table only carries
compound/track_status/stint_index, whereas the rich stint-derived columns
(degradation slope, clean-air pace, traffic, gap-to-car-ahead) exist only in the
local dump at Data/Car_Tyre_CSV/supabase_csv/. tracks.csv likewise already
contains the SC/VSC/red-flag rates and an overtaking score.

The CSV dump uses its own keys, and its `round` numbers are synthetic, so rows
are resolved to the live schema by *natural keys*:
  * stints  -> race_event via (season, grand_prix_name); driver via driver_code
  * profile -> circuit via grand_prix_name

Run:
  python -m strategy.build_profiles --all          # build both, upsert
  python -m strategy.build_profiles --stints       # stints only
  python -m strategy.build_profiles --profiles     # profiles only
  python -m strategy.build_profiles --all --dry-run # compute + print, no writes
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from data_pipeline.db.supabase_client import get_client

_CSV_DIR = Path(__file__).resolve().parents[1] / "Data" / "Car_Tyre_CSV" / "supabase_csv"

_PIT_LOSS_CLAMP = (14.0, 32.0)  # plausible green-flag pit-loss range (seconds)


# ── live lookup maps ─────────────────────────────────────────────────────────

def _load_live_maps(client: Any) -> dict[str, dict]:
    events = _paged(client, "race_events", "id,season,round,grand_prix_name,circuit_id")
    drivers = _paged(client, "drivers", "id,driver_code")
    entries = _paged(client, "driver_race_entries", "id,race_id,driver_id")

    season_gp_to_event = {
        (int(e["season"]), e["grand_prix_name"]): e["id"]
        for e in events if e.get("season") is not None and e.get("grand_prix_name")
    }
    gp_to_circuit = {
        e["grand_prix_name"]: e["circuit_id"]
        for e in events if e.get("grand_prix_name") and e.get("circuit_id")
    }
    code_to_driver = {d["driver_code"]: d["id"] for d in drivers if d.get("driver_code")}
    event_driver_to_entry = {
        (e["race_id"], e["driver_id"]): e["id"]
        for e in entries if e.get("race_id") and e.get("driver_id")
    }
    return {
        "season_gp_to_event": season_gp_to_event,
        "gp_to_circuit": gp_to_circuit,
        "code_to_driver": code_to_driver,
        "event_driver_to_entry": event_driver_to_entry,
    }


# ── track_strategy_profiles ──────────────────────────────────────────────────

def build_track_profiles(client: Any, maps: dict[str, dict]) -> list[dict[str, Any]]:
    tracks = pd.read_csv(_CSV_DIR / "tracks.csv")
    races = pd.read_csv(_CSV_DIR / "races.csv")

    pit_loss_by_gp = _pit_loss_by_gp()
    races_per_gp = races.groupby("gp_name")["season"].nunique().to_dict()

    # Fallback overtaking scale from avg_overtakes when track_score is missing.
    ov = pd.to_numeric(tracks["track_avg_overtakes"], errors="coerce")
    ov_min, ov_max = float(ov.min()), float(ov.max())

    rows: list[dict[str, Any]] = []
    for _, t in tracks.iterrows():
        gp = t["gp_name"]
        circuit_id = maps["gp_to_circuit"].get(gp)
        if circuit_id is None:
            continue  # not a live race weekend (testing, unmapped name)

        score = _f(t.get("track_score"))
        avg_overtakes = _f(t.get("track_avg_overtakes"))
        if score is not None:
            difficulty = _clamp01(1.0 - score / 100.0)
        elif avg_overtakes is not None and ov_max > ov_min:
            difficulty = _clamp01(1.0 - (avg_overtakes - ov_min) / (ov_max - ov_min))
        else:
            difficulty = None

        profile = {
            "circuit_id": int(circuit_id),
            "overtaking_difficulty": _round(difficulty),
            # Track position matters most where passing is hard.
            "track_position_importance": _round(difficulty),
            # Undercut is a heuristic of overtaking difficulty (documented).
            "undercut_strength": _round(_clamp01(0.25 + 0.6 * difficulty)) if difficulty is not None else None,
            "pit_loss_baseline": pit_loss_by_gp.get(gp),
            "sc_prior": _pct(t.get("track_sc_pct")),
            "vsc_prior": _pct(t.get("track_vsc_pct")),
            "red_flag_prior": _pct(t.get("track_red_pct")),
            "sample_races": int(races_per_gp.get(gp, 0)) or None,
        }
        rows.append(profile)
    return rows


def _pit_loss_by_gp() -> dict[str, float]:
    """
    Estimate per-circuit green-flag pit loss from laps.csv: for each pit-ending
    stint, the in-lap (last lap of the stint) runs slower than the stint's
    clean-air average by roughly the pit loss. Median per grand prix, clamped.
    """
    laps = pd.read_csv(_CSV_DIR / "laps.csv")
    entries = pd.read_csv(_CSV_DIR / "driver_race_entries.csv")[["id", "race_id"]]
    races = pd.read_csv(_CSV_DIR / "races.csv")[["id", "gp_name"]]

    laps = laps[_as_bool(laps["stint_pit_ended"])].copy()
    laps["lap_time"] = pd.to_numeric(laps["lap_time"], errors="coerce")
    laps["stint_clean_air_avg"] = pd.to_numeric(laps["stint_clean_air_avg"], errors="coerce")

    # In-lap = last lap of each (entry, stint).
    laps = laps.sort_values("lap_number")
    inlaps = laps.groupby(["driver_race_entry_id", "stint_index"], as_index=False).last()
    inlaps["pit_delta"] = inlaps["lap_time"] - inlaps["stint_clean_air_avg"]
    inlaps = inlaps[(inlaps["pit_delta"] > 8) & (inlaps["pit_delta"] < 45)]

    merged = (
        inlaps.merge(entries, left_on="driver_race_entry_id", right_on="id", how="left")
        .merge(races, left_on="race_id", right_on="id", how="left")
    )
    out: dict[str, float] = {}
    for gp, grp in merged.groupby("gp_name"):
        med = float(np.median(grp["pit_delta"]))
        out[gp] = round(min(max(med, _PIT_LOSS_CLAMP[0]), _PIT_LOSS_CLAMP[1]), 3)
    return out


# ── driver_race_stints ───────────────────────────────────────────────────────

def build_stints(client: Any, maps: dict[str, dict]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    laps = pd.read_csv(_CSV_DIR / "laps.csv")
    entries = pd.read_csv(_CSV_DIR / "driver_race_entries.csv")[["id", "race_id", "driver_id"]]
    races = pd.read_csv(_CSV_DIR / "races.csv")[["id", "season", "gp_name"]]
    drivers = pd.read_csv(_CSV_DIR / "drivers.csv")[["id", "driver_code"]]

    for col in ("lap_time", "interval_to_car_ahead", "stint_deg_slope",
                "stint_clean_air_avg", "stint_length", "stint_start_lap",
                "stint_end_lap", "lap_number", "stint_index"):
        if col in laps.columns:
            laps[col] = pd.to_numeric(laps[col], errors="coerce")
    laps["in_traffic_b"] = _as_bool(laps["in_traffic"])
    laps["pit_ended_b"] = _as_bool(laps["stint_pit_ended"])

    # CSV linkage maps.
    csv_entry = entries.set_index("id")
    csv_race = races.set_index("id")
    csv_driver = drivers.set_index("id")["driver_code"].to_dict()

    skipped = {"no_entry": 0, "no_race": 0, "no_driver": 0, "no_event": 0}
    rows: list[dict[str, Any]] = []

    grouped = laps.groupby(["driver_race_entry_id", "stint_index"], sort=False)
    for (entry_id, stint_idx), grp in grouped:
        if pd.isna(stint_idx):
            continue
        if entry_id not in csv_entry.index:
            skipped["no_entry"] += 1
            continue
        ent = csv_entry.loc[entry_id]
        csv_race_id = ent["race_id"]
        csv_driver_id = ent["driver_id"]

        if csv_race_id not in csv_race.index:
            skipped["no_race"] += 1
            continue
        race = csv_race.loc[csv_race_id]
        season, gp = race["season"], race["gp_name"]

        driver_code = csv_driver.get(csv_driver_id)
        live_driver_id = maps["code_to_driver"].get(driver_code)
        if live_driver_id is None:
            skipped["no_driver"] += 1
            continue

        live_event_id = maps["season_gp_to_event"].get((int(season), gp)) if pd.notna(season) else None
        if live_event_id is None:
            skipped["no_event"] += 1
            continue

        live_entry_id = maps["event_driver_to_entry"].get((live_event_id, live_driver_id))

        rows.append(_stint_row(grp, int(stint_idx), live_event_id, live_driver_id, live_entry_id))

    return rows, skipped


def _stint_row(grp: pd.DataFrame, stint_idx: int, event_id: int,
               driver_id: str, entry_id: Optional[str]) -> dict[str, Any]:
    first = grp.iloc[0]
    start = _i(first.get("stint_start_lap")) or _i(grp["lap_number"].min())
    end = _i(first.get("stint_end_lap")) or _i(grp["lap_number"].max())
    length = _i(first.get("stint_length")) or int(len(grp))

    clean_air = _f(first.get("stint_clean_air_avg"))
    if clean_air is None:
        clean_laps = grp.loc[~grp["in_traffic_b"], "lap_time"].dropna()
        clean_air = float(clean_laps.mean()) if len(clean_laps) else None

    gap = grp["interval_to_car_ahead"].dropna()
    return {
        "race_event_id": event_id,
        "driver_id": driver_id,
        "driver_race_entry_id": entry_id,
        "stint_index": stint_idx,
        "compound": str(first.get("compound") or "UNKNOWN").upper(),
        "lap_window_start": start or 0,
        "lap_window_end": end or 0,
        "stint_length": length or 0,
        "degradation_slope": _round(_f(first.get("stint_deg_slope")), 5),
        "clean_air_pace": _round(clean_air, 4),
        "traffic_share": _round(float(grp["in_traffic_b"].mean()), 4),
        "gap_to_car_ahead": _round(float(gap.mean()), 4) if len(gap) else None,
        "pit_ended": bool(first.get("pit_ended_b")),
    }


# ── upserts ────────────────────────────────────────────────────────────────

def _upsert(client: Any, table: str, rows: list[dict], conflict: str, batch: int = 500) -> None:
    for i in range(0, len(rows), batch):
        client.table(table).upsert(rows[i:i + batch], on_conflict=conflict).execute()


# ── helpers ────────────────────────────────────────────────────────────────

def _paged(client: Any, table: str, fields: str, page_size: int = 1000) -> list[dict]:
    rows, start = [], 0
    while True:
        batch = (
            client.table(table).select(fields).range(start, start + page_size - 1).execute().data or []
        )
        rows.extend(batch)
        if len(batch) < page_size:
            break
        start += page_size
    return rows


def _as_bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin(("true", "1", "t", "yes"))


def _f(v) -> Optional[float]:
    try:
        f = float(v)
        return None if np.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _i(v) -> Optional[int]:
    f = _f(v)
    return int(round(f)) if f is not None else None


def _round(v: Optional[float], ndigits: int = 4) -> Optional[float]:
    return round(v, ndigits) if v is not None else None


def _clamp01(v: Optional[float]) -> Optional[float]:
    return None if v is None else max(0.0, min(1.0, v))


def _pct(v) -> Optional[float]:
    """Convert a 0..100 percentage column to a 0..1 probability."""
    f = _f(v)
    return None if f is None else round(_clamp01(f / 100.0), 4)


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Build strategy tables from the local CSV dump.")
    parser.add_argument("--all", action="store_true", help="Build both stints and profiles.")
    parser.add_argument("--stints", action="store_true", help="Build driver_race_stints.")
    parser.add_argument("--profiles", action="store_true", help="Build track_strategy_profiles.")
    parser.add_argument("--dry-run", action="store_true", help="Compute and print counts; do not write.")
    args = parser.parse_args()

    do_stints = args.all or args.stints
    do_profiles = args.all or args.profiles
    if not (do_stints or do_profiles):
        parser.error("Choose --all, --stints, and/or --profiles.")

    client = get_client()
    maps = _load_live_maps(client)

    if do_profiles:
        profiles = build_track_profiles(client, maps)
        print(f"track_strategy_profiles: {len(profiles)} rows resolved to live circuits")
        if not args.dry_run:
            _upsert(client, "track_strategy_profiles", profiles, "circuit_id")
            print("  upserted.")

    if do_stints:
        stints, skipped = build_stints(client, maps)
        print(f"driver_race_stints: {len(stints)} rows resolved; skipped {skipped}")
        if not args.dry_run:
            _upsert(client, "driver_race_stints", stints, "race_event_id,driver_id,stint_index")
            print("  upserted.")


if __name__ == "__main__":
    main()

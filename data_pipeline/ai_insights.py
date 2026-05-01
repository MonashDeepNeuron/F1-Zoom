from __future__ import annotations

import hashlib
import json
import os
import re
import ssl
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import certifi
from dotenv import load_dotenv

from data_pipeline.db.supabase_client import get_client

load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)

DEFAULT_GEMINI_MODEL = "gemini-2.5-flash-lite"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

DRIVER_CONTEXT_FIELDS = (
    "fp1_pos",
    "fp2_pos",
    "fp3_pos",
    "qualifying_pos",
    "qualifying_final_grid_pos",
    "q1_position",
    "q2_position",
    "q3_position",
    "sprint_qualifying_final_grid_pos",
    "sprint_finish_pos",
    "driver_clean_air_pace",
    "driver_grid_avg_pace",
    "driver_pace_delta_to_grid",
    "driver_pace_score_vs_grid",
    "driver_pace_score_0_100",
    "driver_top_speed_rank",
    "driver_corner_speed_rank",
    "avg_race_pos_3_races",
    "avg_race_pos_5_races",
    "avg_race_pos_7_races",
)

HISTORY_CONTEXT_FIELDS = (
    "race_finish_pos",
    "race_status",
    "position_gain_from_quali_to_race",
    "driver_avg_pace",
    "driver_clean_air_pace",
    "driver_grid_avg_pace",
    "driver_pace_delta_to_grid",
    "driver_pace_score_vs_grid",
    "driver_pace_score_0_100",
    "driver_top_speed",
    "driver_corner_speed",
    "driver_top_speed_rank",
    "driver_corner_speed_rank",
    "driver_drag_index",
)


def generate_prediction_insight(
    results_df: pd.DataFrame,
    season: int,
    race_name: str,
) -> dict[str, Any] | None:
    """
    Generate and cache a single AI explanation for the race prediction.

    The insight is race-level, not user-level, so every fan sees the same copy.
    Failures are logged and swallowed so prediction generation can still finish.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("AI insight skipped: GEMINI_API_KEY is not set")
        return None

    if results_df.empty:
        print("AI insight skipped: no prediction rows were supplied")
        return None

    client = get_client()
    race_event = _get_race_event(client, season, race_name)
    if race_event is None:
        print(f"AI insight skipped: no race_event found for {season} {race_name}")
        return None

    race_event_id = race_event["id"]
    payload = _build_payload(client, race_event, results_df)
    input_hash = _hash_payload(payload)
    model_name = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)

    cached = _get_cached_insight(client, race_event_id)
    if cached and cached.get("input_hash") == input_hash:
        print("AI insight unchanged; using cached Supabase row")
        return cached

    try:
        insight = _request_gemini_insight(api_key, model_name, payload)
        row = {
            "race_event_id": race_event_id,
            "predicted_winner": payload["predictions"][0]["driver"],
            "model_name": model_name,
            "input_hash": input_hash,
            "summary": insight["summary"],
            "key_reasons": insight["key_reasons"],
            "contenders": insight["contenders"],
            "caveats": insight["caveats"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
        result = (
            client.table("prediction_insights")
            .upsert(row, on_conflict="race_event_id")
            .execute()
        )
        print(f"AI insight upserted to Supabase for {season} {race_name}")
        return result.data[0] if result.data else row
    except Exception as exc:
        print(f"AI insight generation failed: {exc}")
        return None


def _get_race_event(client: Any, season: int, race_name: str) -> dict[str, Any] | None:
    result = (
        client.table("race_events")
        .select("id,season,round,grand_prix_name,circuits(title,subtitle,weekend_format,length_km,laps,corners)")
        .eq("season", season)
        .eq("grand_prix_name", race_name)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _get_cached_insight(client: Any, race_event_id: int) -> dict[str, Any] | None:
    result = (
        client.table("prediction_insights")
        .select("*")
        .eq("race_event_id", race_event_id)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def _build_payload(
    client: Any,
    race_event: dict[str, Any],
    results_df: pd.DataFrame,
) -> dict[str, Any]:
    driver_context = _fetch_driver_context(client, race_event["id"])
    driver_codes = [
        str(row.get("driver"))
        for _, row in results_df.iterrows()
        if _clean(row.get("driver")) is not None
    ]
    recent_history = _fetch_recent_driver_history(client, race_event, driver_codes)
    driver_summaries = _summarize_driver_history(recent_history)
    team_summaries = _summarize_team_history(recent_history)
    predictions = []

    for _, row in results_df.sort_values("predicted_position").iterrows():
        driver_code = _clean(row.get("driver"))
        item = {
            "predictedPosition": _clean(row.get("predicted_position")),
            "driver": driver_code,
            "team": _clean(row.get("team")),
            "gridPosition": _clean(row.get("grid_pos")),
            "predictionScore": _clean(row.get("prediction_score")),
        }
        if driver_code in driver_context:
            item["currentRaceData"] = driver_context[driver_code]
        if driver_code in driver_summaries:
            driver_name = driver_summaries[driver_code].get("driverName")
            if driver_name:
                item["driverName"] = driver_name
            item["recentForm"] = driver_summaries[driver_code]
        predictions.append(item)

    contender_candidates = [
        item for item in predictions if item.get("predictedPosition") in (2, 3, 4)
    ]

    return {
        "race": {
            "raceEventId": race_event["id"],
            "season": race_event["season"],
            "round": race_event["round"],
            "grandPrixName": race_event["grand_prix_name"],
            "circuit": race_event.get("circuits") or {},
        },
        "dataAvailability": {
            "currentRaceDriverRows": len(driver_context),
            "note": (
                "currentRaceData is empty until practice, qualifying, or race data "
                "has been fetched for this race"
            ),
        },
        "teamRecentForm": team_summaries,
        "winnerCandidate": predictions[0] if predictions else None,
        "contenderCandidates": contender_candidates,
        "predictions": predictions,
    }


def _fetch_driver_context(client: Any, race_event_id: int) -> dict[str, dict[str, Any]]:
    select_fields = ",".join((
        "drivers(driver_code,full_name)",
        *DRIVER_CONTEXT_FIELDS,
    ))
    result = (
        client.table("driver_race_entries")
        .select(select_fields)
        .eq("race_id", race_event_id)
        .execute()
    )

    context = {}
    for row in result.data or []:
        driver = row.get("drivers") or {}
        driver_code = driver.get("driver_code")
        if not driver_code:
            continue

        metrics = {
            _to_camel_case(field): _clean(row.get(field))
            for field in DRIVER_CONTEXT_FIELDS
            if _clean(row.get(field)) is not None
        }
        full_name = _clean(driver.get("full_name"))
        if full_name:
            metrics["driverName"] = full_name
        context[driver_code] = metrics

    return context


def _fetch_recent_driver_history(
    client: Any,
    race_event: dict[str, Any],
    driver_codes: list[str],
) -> dict[str, list[dict[str, Any]]]:
    if not driver_codes:
        return {}

    select_fields = ",".join((
        "drivers!inner(driver_code,full_name)",
        "teams(team_name)",
        "race_events!inner(season,round,grand_prix_name)",
        *HISTORY_CONTEXT_FIELDS,
    ))
    result = (
        client.table("driver_race_entries")
        .select(select_fields)
        .in_("drivers.driver_code", driver_codes)
        .eq("race_events.season", race_event["season"])
        .lt("race_events.round", race_event["round"])
        .execute()
    )

    by_driver: dict[str, list[dict[str, Any]]] = {driver: [] for driver in driver_codes}
    for row in result.data or []:
        race = row.get("race_events") or {}
        driver = row.get("drivers") or {}
        team = row.get("teams") or {}
        driver_code = driver.get("driver_code")
        if not driver_code or not race:
            continue

        history_row = {
            "race": race.get("grand_prix_name"),
            "round": _clean(race.get("round")),
            "team": team.get("team_name"),
            "driverName": driver.get("full_name"),
        }
        for field in HISTORY_CONTEXT_FIELDS:
            cleaned = _clean(row.get(field))
            if cleaned is not None:
                history_row[_to_camel_case(field)] = cleaned
        by_driver.setdefault(driver_code, []).append(history_row)

    for rows in by_driver.values():
        rows.sort(key=lambda item: item.get("round") or 0)

    return by_driver


def _summarize_driver_history(
    recent_history: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    summaries = {}
    for driver_code, rows in recent_history.items():
        finishes = [
            int(row["raceFinishPos"])
            for row in rows
            if row.get("raceFinishPos") is not None
        ]
        pace_scores = _numeric_values(rows, "driverPaceScore0100")
        clean_air_paces = _numeric_values(rows, "driverCleanAirPace")
        corner_ranks = _numeric_values(rows, "driverCornerSpeedRank")
        top_speed_ranks = _numeric_values(rows, "driverTopSpeedRank")
        corner_speeds = _numeric_values(rows, "driverCornerSpeed")
        top_speeds = _numeric_values(rows, "driverTopSpeed")

        summary = {
            "driverName": next(
                (row.get("driverName") for row in rows if row.get("driverName")),
                None,
            ),
            "races": rows,
            "completedRaces": len(finishes),
            "wins": sum(1 for finish in finishes if finish == 1),
            "podiums": sum(1 for finish in finishes if finish <= 3),
            "topFiveFinishes": sum(1 for finish in finishes if finish <= 5),
            "allCompletedRacesWerePodiums": bool(finishes) and all(
                finish <= 3 for finish in finishes
            ),
            "finishTrend": _finish_trend(rows),
            "evidence": [],
        }
        if finishes:
            summary["averageFinish"] = round(sum(finishes) / len(finishes), 2)
            summary["bestFinish"] = min(finishes)
            summary["latestFinish"] = finishes[-1]
        if pace_scores:
            summary["averagePaceScore0100"] = round(
                sum(pace_scores) / len(pace_scores), 2
            )
            summary["bestPaceScore0100"] = round(max(pace_scores), 2)
        if clean_air_paces:
            summary["averageCleanAirRacePace"] = round(
                sum(clean_air_paces) / len(clean_air_paces), 4
            )
        if corner_ranks:
            summary["averageCornerSpeedRank"] = round(
                sum(corner_ranks) / len(corner_ranks), 2
            )
            summary["bestCornerSpeedRank"] = int(min(corner_ranks))
        if top_speed_ranks:
            summary["averageTopSpeedRank"] = round(
                sum(top_speed_ranks) / len(top_speed_ranks), 2
            )
            summary["bestTopSpeedRank"] = int(min(top_speed_ranks))
        if corner_speeds:
            summary["bestCornerSpeed"] = round(max(corner_speeds), 2)
        if top_speeds:
            summary["bestTopSpeed"] = round(max(top_speeds), 2)

        summary["evidence"] = _driver_evidence(summary, rows)
        summaries[driver_code] = summary

    return summaries


def _summarize_team_history(
    recent_history: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, Any]]:
    team_rows: dict[str, list[dict[str, Any]]] = {}
    for rows in recent_history.values():
        for row in rows:
            team = row.get("team")
            if team:
                team_rows.setdefault(team, []).append(row)

    summaries = {}
    for team, rows in team_rows.items():
        finishes = [
            int(row["raceFinishPos"])
            for row in rows
            if row.get("raceFinishPos") is not None
        ]
        pace_scores = _numeric_values(rows, "driverPaceScore0100")
        corner_ranks = _numeric_values(rows, "driverCornerSpeedRank")
        top_speed_ranks = _numeric_values(rows, "driverTopSpeedRank")
        rounds = sorted({
            int(row["round"]) for row in rows if row.get("round") is not None
        })
        summary = {
            "roundsCovered": rounds,
            "classifiedFinishes": len(finishes),
            "wins": sum(1 for finish in finishes if finish == 1),
            "podiums": sum(1 for finish in finishes if finish <= 3),
            "topFiveFinishes": sum(1 for finish in finishes if finish <= 5),
        }
        if finishes:
            summary["averageFinish"] = round(sum(finishes) / len(finishes), 2)
        if pace_scores:
            summary["averagePaceScore0100"] = round(
                sum(pace_scores) / len(pace_scores), 2
            )
        if corner_ranks:
            summary["averageCornerSpeedRank"] = round(
                sum(corner_ranks) / len(corner_ranks), 2
            )
            summary["bestCornerSpeedRank"] = int(min(corner_ranks))
        if top_speed_ranks:
            summary["averageTopSpeedRank"] = round(
                sum(top_speed_ranks) / len(top_speed_ranks), 2
            )
            summary["bestTopSpeedRank"] = int(min(top_speed_ranks))

        summaries[team] = summary

    return summaries


def _driver_evidence(
    summary: dict[str, Any],
    rows: list[dict[str, Any]],
) -> list[str]:
    evidence = []
    finish_trend = summary.get("finishTrend")
    if finish_trend:
        evidence.append(f"Recent 2026 finishes: {finish_trend}")

    completed = summary.get("completedRaces", 0)
    if completed:
        podiums = summary.get("podiums", 0)
        wins = summary.get("wins", 0)
        evidence.append(
            f"{podiums} {_plural('podium', podiums)} and {wins} {_plural('win', wins)} "
            f"from {completed} {_plural('completed race', completed)}"
        )

    if summary.get("averagePaceScore0100") is not None:
        evidence.append(
            f"Average recent pace score: {summary['averagePaceScore0100']}/100"
        )

    if summary.get("averageCleanAirRacePace") is not None:
        evidence.append(
            f"Average recent clean-air race pace: {summary['averageCleanAirRacePace']}"
        )

    corner_bits = []
    if summary.get("bestCornerSpeedRank") is not None:
        corner_bits.append(f"best corner-speed rank P{summary['bestCornerSpeedRank']}")
    if summary.get("averageCornerSpeedRank") is not None:
        corner_bits.append(f"average corner-speed rank {summary['averageCornerSpeedRank']}")
    if corner_bits:
        evidence.append("; ".join(corner_bits))

    top_speed_bits = []
    if summary.get("bestTopSpeedRank") is not None:
        top_speed_bits.append(f"best top-speed rank P{summary['bestTopSpeedRank']}")
    if summary.get("averageTopSpeedRank") is not None:
        top_speed_bits.append(f"average top-speed rank {summary['averageTopSpeedRank']}")
    if top_speed_bits:
        evidence.append("; ".join(top_speed_bits))

    missing_clean_air = rows and all(row.get("driverCleanAirPace") is None for row in rows)
    if missing_clean_air:
        evidence.append("Clean-air race pace is not available in the recent rows")

    return evidence


def _finish_trend(rows: list[dict[str, Any]]) -> str | None:
    parts = []
    for row in rows:
        finish = row.get("raceFinishPos")
        race = row.get("race")
        if finish is None or not race:
            continue
        short_name = str(race).replace(" Grand Prix", "")
        parts.append(f"P{finish} {short_name}")
    return ", ".join(parts) if parts else None


def _numeric_values(rows: list[dict[str, Any]], field: str) -> list[float]:
    values = []
    for row in rows:
        value = row.get(field)
        if value is None:
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values


def _plural(label: str, count: int) -> str:
    return label if count == 1 else f"{label}s"


def _request_gemini_insight(
    api_key: str,
    model_name: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    prompt = (
        "Create a data-led Formula 1 prediction insight from this JSON.\n"
        "Write for fans, but make the reasoning come from the supplied metrics: recent "
        "finishes, podium/win counts, pace score, clean-air race pace when available, "
        "corner-speed rank, top-speed rank, drag index, team recent form, circuit length, "
        "laps, and corners. Prefer specific facts like '2 podiums from 3 races' or "
        "'best corner-speed rank P1' over generic ranking language. If currentRaceData "
        "is empty, say the view is based on recent-season form and do not imply current "
        "weekend practice, qualifying, or clean-air data exists. Mention track style only "
        "when it is directly supported by the circuit name/subtitle in the JSON. "
        "Do not say a driver has finished on the podium every race unless "
        "allCompletedRacesWerePodiums is true.\n"
        "winnerCandidate is the predicted winner. The summary must use winnerCandidate "
        "for winner-specific facts and must not borrow wins, podiums, pace scores, or "
        "speed ranks from contenderCandidates or other drivers. Copy numeric claims "
        "exactly from the relevant driver's recentForm fields/evidence; if unsure, omit "
        "the number.\n"
        "The summary should be 2-4 sentences. key_reasons should be 3-5 specific, "
        "data-backed bullets. contenders should explain why the closest challengers are "
        "dangerous, not just list names. Use only contenderCandidates for contenders. "
        "Use driverName when supplied; otherwise use the driver code. caveats should call "
        "out missing current data, tied prediction scores, or weak evidence where applicable.\n"
        "Return exactly this JSON shape: "
        '{"summary": string, "key_reasons": string[], "contenders": string[], "caveats": string[]}.\n\n'
        f"{json.dumps(payload, sort_keys=True, separators=(',', ':'))}"
    )
    request_body = {
        "system_instruction": {
            "parts": [{
                "text": (
                    "You write factual, data-led Formula 1 race prediction insights for fans. "
                    "Use only the supplied JSON. Do not invent news, penalties, weather, "
                    "setup changes, injuries, strategy, or telemetry that is not present. "
                    "Do not overclaim from missing data. Return strict JSON only."
                )
            }]
        },
        "contents": [{
            "parts": [{"text": prompt}]
        }],
        "generationConfig": {
            "temperature": 0.25,
            "responseMimeType": "application/json",
        },
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

    try:
        ssl_context = ssl.create_default_context(cafile=certifi.where())
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

    return _validate_insight(_parse_json_text(text))


def _parse_json_text(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    parsed = json.loads(cleaned)
    if not isinstance(parsed, dict):
        raise RuntimeError("Gemini insight response was not a JSON object")
    return parsed


def _validate_insight(raw: dict[str, Any]) -> dict[str, Any]:
    summary = str(raw.get("summary", "")).strip()
    if not summary:
        raise RuntimeError("Gemini insight was missing summary")

    return {
        "summary": summary[:1400],
        "key_reasons": _string_list(raw.get("key_reasons"), limit=5),
        "contenders": _string_list(raw.get("contenders"), limit=4),
        "caveats": _string_list(raw.get("caveats"), limit=4),
    }


def _string_list(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []

    output = []
    for item in value[:limit]:
        text = str(item).strip()
        if text:
            output.append(text[:360])
    return output


def _hash_payload(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _clean(value: Any) -> Any:
    if value is None:
        return None
    if pd.isna(value):
        return None
    if hasattr(value, "item"):
        return value.item()
    return value


def _to_camel_case(name: str) -> str:
    parts = name.split("_")
    return parts[0] + "".join(part.title() for part in parts[1:])

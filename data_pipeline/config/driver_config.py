"""
Shared driver/team configuration loader.

Single source of truth for driver numbers, team assignments, mid-season
swaps, sprint weekends, and number aliases across all seasons.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Dict, Optional


_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "driver_teams.json")


@lru_cache(maxsize=1)
def _load_config() -> dict:
    with open(_CONFIG_PATH) as f:
        return json.load(f)


def get_team_from_driver(driver_code: str, season: int, race_number: int = 1) -> str:
    """
    Resolve the team for *driver_code* in *season* at *race_number*,
    respecting first_round / last_round bounds and per-round overrides.
    """
    config = _load_config()
    season_data = config.get(str(season), {})
    driver_data = season_data.get(driver_code)

    if not driver_data or not isinstance(driver_data, dict):
        return "Unknown Team"

    default_team = driver_data.get("team")
    if default_team is None:
        return "Unknown Team"

    first_round = driver_data.get("first_round", 1)
    last_round = driver_data.get("last_round", 99)
    if race_number < first_round or race_number > last_round:
        return "Unknown Team"

    for override in driver_data.get("overrides", []):
        if "rounds" in override and race_number in override["rounds"]:
            return override["team"]
        if "max_round" in override and race_number <= override["max_round"]:
            return override["team"]
        if "min_round" in override and race_number >= override["min_round"]:
            return override["team"]

    return default_team


def get_driver_from_number(driver_number: int, season: int = 2025) -> str:
    """
    Map a car number back to a three-letter driver code.
    Checks number_aliases first (e.g. FP1 test numbers), then the season roster.
    """
    config = _load_config()

    alias = config.get("number_aliases", {}).get(str(driver_number))
    if alias:
        return alias

    season_data = config.get(str(season), {})
    for code, data in season_data.items():
        if isinstance(data, dict) and data.get("number") == driver_number:
            return code

    return "Unknown"


def get_number_from_driver(driver_code: str, season: int = 2025) -> int:
    """Return the car number for a driver code, or -1 if not found."""
    config = _load_config()
    season_data = config.get(str(season), {})
    driver_data = season_data.get(driver_code)
    if driver_data and isinstance(driver_data, dict):
        return driver_data.get("number", -1)
    return -1


def is_sprint_weekend(race_name: str, season: int = 2025) -> bool:
    """Return True if *race_name* is a sprint weekend in the given season."""
    config = _load_config()
    sprint_races = config.get("sprint_weekends", {}).get(str(season), [])
    return race_name in sprint_races


def get_driver_numbers(season: int = 2025) -> Dict[str, int]:
    """Return {driver_code: number} for every driver in the season."""
    config = _load_config()
    season_data = config.get(str(season), {})
    return {
        code: data["number"]
        for code, data in season_data.items()
        if isinstance(data, dict) and "number" in data
    }


def get_driver_teams(season: int = 2025) -> Dict[str, str]:
    """Return {driver_code: team} for every driver in the season (default team only)."""
    config = _load_config()
    season_data = config.get(str(season), {})
    return {
        code: data["team"]
        for code, data in season_data.items()
        if isinstance(data, dict) and data.get("team")
    }

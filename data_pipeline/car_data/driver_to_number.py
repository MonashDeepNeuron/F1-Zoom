"""
Thin wrapper kept for backward-compatibility with notebooks that do:
    from driver_to_number import driver_to_number
All data now lives in data_pipeline/config/driver_teams.json.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config'))
from driver_config import get_driver_numbers, get_number_from_driver, get_driver_from_number

driver_to_number = get_driver_numbers(season=2025)


def get_number_from_driver_code(driver_code: str) -> int:
    return get_number_from_driver(driver_code, season=2025)


def get_driver_from_number_code(driver_number: int) -> str:
    return get_driver_from_number(driver_number, season=2025)

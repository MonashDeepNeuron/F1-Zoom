"""
Thin wrapper kept for backward-compatibility with notebooks that do:
    from driver_to_team import driver_to_team
All data now lives in data_pipeline/config/driver_teams.json.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config'))
from driver_config import get_driver_teams, get_team_from_driver

driver_to_team = get_driver_teams(season=2025)

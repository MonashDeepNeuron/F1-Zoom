from __future__ import annotations

import fastf1
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Optional

columns = [
    "season", "race_name", "team", "driver",
    "lap_number", "stint_index", "compound",
    "lap_time",

    # traffic
    "interval_to_car_ahead",   # seconds
    "in_traffic",              # boolean
]


@dataclass
class LapRecord:
    season: int # collected
    race_name: str # collected
    
    team: str
    driver: str # collected
    
    lap_number: int # collected through the index of the laps array
    stint_index: int
    compound: str
    lap_time: float  # collected

    interval_to_car_ahead: Optional[float]  # seconds, NaN if none
    in_traffic: bool
    
    
class LapDataLoader:
    """
    Collecting per lap metrics for F1 races in the 2025 Season
    """
    
    
    def __init__(self, cache_dir= "fastf1_cache", traffic_interval_threshold=3.0) -> None:
        fastf1.Cache.enable_cache(cache_dir)
        self.traffic_interval_threshold = traffic_interval_threshold
    
    
    def collect_session_lap_data(self, season, round, session_type="R") -> pd.DataFrame:
        session = fastf1.get_session(season, round, session_type)
        session.load(laps=True, telemetry=False)
        
        records = []
        
        race_name = session.event['circuit_short_name']
        laps = session.laps
        
        for drv in laps['driver_number'].unique():
            driver_number = drv
            
            # now we are storing the data for each drivers laps
            driver_laps = laps[laps['driver_number'] == driver_number]
            
            
            driver_lap_time = driver_laps['lap_duration'] # array of all driber lap times - will give us 91.743 for example
            
            
            

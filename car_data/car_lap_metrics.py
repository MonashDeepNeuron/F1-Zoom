from __future__ import annotations

import fastf1
import pandas as pd
import numpy as np
import requests
from dataclasses import dataclass
from typing import List, Optional
from datetime import timedelta

from driver_to_team import get_team_from_driver
from driver_to_number import get_number_from_driver, get_driver_from_number

columns = [
    "season", "race_name", "team", "driver",
    "lap_number", "stint_index", "compound",
    "lap_time",

    # traffic
    "interval_to_car_ahead",   # seconds
    "in_traffic",              # boolean
]

BASE_URL = "https://api.openf1.org/v1"



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
    
    ### HELPER FUNCTIONS ###
    def _fetch_df(self, endpoint: str, **params) -> pd.DataFrame:
        url = f"{BASE_URL}/{endpoint}"
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        if not data:
            return pd.DataFrame()
        return pd.DataFrame(data)

    def _get_race_name(self, meeting_key: int) -> str:
        """
        Grab the circuit_short_name for a meeting_key.
        """
        df = self._fetch_df("meetings", meeting_key=meeting_key)
        if df.empty:
            return "Unknown"
        return str(df.iloc[0]["circuit_short_name"])

    def _find_stint_for_lap(
        self,
        stints: pd.DataFrame,
        driver_number: int,
        lap_number: int,
    ) -> tuple[int, str]:
        """
        Find which stint this lap belongs to for a driver.
        Return (stint_number, compound).
        """
        if stints.empty:
            return 0, "UNKNOWN"

        driver_stints = stints[stints["driver_number"] == driver_number]
        mask = (driver_stints["lap_start"] <= lap_number) & (
            driver_stints["lap_end"] >= lap_number
        )
        row = driver_stints[mask]

        if row.empty:
            return 0, "UNKNOWN"

        row = row.iloc[0]
        return int(row["stint_number"]), str(row["compound"])

    def _find_interval_for_lap(
        self,
        intervals: pd.DataFrame,
        driver_number: int,
        lap_start_time: pd.Timestamp,
        lap_duration: float,
    ) -> tuple[Optional[float], bool]:
        """
        Approximate interval to car ahead by:
          - taking the midpoint of the lap in time
          - finding the closest /intervals row in time
        """
        if intervals.empty:
            return np.nan, False

        driver_int = intervals[intervals["driver_number"] == driver_number]
        if driver_int.empty:
            return np.nan, False

        mid_time = lap_start_time + timedelta(seconds=lap_duration / 2)

        diffs = (driver_int["date"] - mid_time).abs()
        idx = diffs.idxmin()
        row = driver_int.loc[idx]

        val = row["interval"]
        # handle null or "+1 LAP" style strings
        if val is None or (isinstance(val, str) and "LAP" in val):
            return np.nan, False

        try:
            gap = float(val)
        except (TypeError, ValueError):
            return np.nan, False

        in_traffic = gap < self.traffic_interval_threshold
        return gap, in_traffic
    
    
    def collect_session_lap_data(self, season, meeting_key, session_key="R") -> pd.DataFrame:

        race_name = self._get_race_name(meeting_key)
        
        
        drivers = self._fetch_df("drivers", session_key=session_key)
        laps = self._fetch_df("laps", session_key=session_key)
        stints = self._fetch_df("stints", session_key=session_key)
        intervals = self._fetch_df("intervals", session_key=session_key)

        
        if not laps.empty:
            laps["date_start"] = pd.to_datetime(laps["date_start"])
            
        if not intervals.empty:
            intervals["date"] = pd.to_datetime(intervals["date"])
        
        records: List[LapRecord] = []
        
        for driver_number in laps['driver_number'].unique():
            # now we are storing the data for each drivers laps
            driver_laps = laps[laps['driver_number'] == driver_number].copy()
            
            team_name = get_team_from_driver(driver_number)
            driver_name = get_driver_from_number(driver_number)
            
            
            for _, lap in driver_laps.iterrows():
                lap_duration = lap["lap_duration"]  # seconds (float)

                if pd.isna(lap_duration):
                    continue

                lap_number = int(lap["lap_number"])
                lap_time_sec = float(lap_duration)

                # the stint / compound this lap is on
                stint_index, compound = self._find_stint_for_lap(stints, driver_number, lap_number)

                # what's the gap to the car ahead in the middle of this lap?
                interval_to_ahead, in_traffic = self._find_interval_for_lap(
                    intervals,
                    driver_number,
                    lap["date_start"],
                    lap_time_sec,
                )

                record = LapRecord(
                    season=season,
                    race_name=race_name,
                    team=team_name,
                    driver=driver_name,
                    lap_number=lap_number,
                    stint_index=stint_index,
                    compound=compound,
                    lap_time=lap_time_sec,
                    interval_to_car_ahead=interval_to_ahead,
                    in_traffic=in_traffic,
                )
                records.append(record)
                
        
        # convert records into a dataframe
        if not records:
            return pd.DataFrame(columns=columns)

        df = pd.DataFrame([r.__dict__ for r in records])
        df = df[columns]

        return df        
                
            
            
            

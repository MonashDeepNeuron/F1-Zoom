from __future__ import annotations
from py_compile import main

import fastf1
import os
import pandas as pd
import numpy as np
import requests
from dataclasses import dataclass
from typing import List, Optional
from datetime import timedelta
import time

driver_to_number = {
    "VER": 1, "NOR": 4, "SAI": 55, "PIA": 81, "ALO": 14,
    "RUS": 63, "HAM": 44, "LEC": 16, "STR": 18, "TSU": 22,
    "ALB": 23, "HUL": 27, "GAS": 10, "OCO": 31, "PER": 11,
    "RIC": 3, "SAR": 2, "BOT": 77, "ZHO": 24, "MAG": 20,
    "ANT": 12, "BEA": 87, "DOO": 7, "COL": 43, "LAW": 30,
    "BOR": 5, "HAD": 6
}

# Season and race-aware team mapping
def get_team_from_driver(driver_code: str, season: int, race_number: int = 1) -> str:
    """
    Get team for a driver based on season and race number.
    
    Args:
        driver_code: Three-letter driver code
        season: Year (2024 or 2025)
        race_number: Race number in the season (1-24)
    """
    # 2024 teams
    if season == 2024:
        teams_2024 = {
            "VER": "Red Bull", "PER": "Red Bull",
            "HAM": "Mercedes", "RUS": "Mercedes",
            "LEC": "Ferrari", "SAI": "Ferrari",
            "BEA": "Ferrari" if race_number == 2 else "Haas",
            "NOR": "McLaren", "PIA": "McLaren",
            "ALO": "Aston Martin", "STR": "Aston Martin",
            "GAS": "Alpine", "OCO": "Alpine", "DOO": "Alpine",
            "ALB": "Williams",
            "SAR": "Williams" if race_number <= 15 else None,
            "COL": "Williams" if race_number >= 16 else None,
            "BOT": "Sauber", "ZHO": "Sauber",
            "MAG": "Haas", "HUL": "Haas",
            "TSU": "RB",
            "RIC": "RB" if race_number <= 18 else None,
            "LAW": "RB" if race_number >= 19 else None,
            "DOO": "Alpine",
        }
        return teams_2024.get(driver_code, "Unknown Team")
    
    # 2025 teams
    elif season == 2025:
        teams_2025 = {
            "VER": "Red Bull",
            "LAW": "Red Bull" if race_number <= 2 else "RB",  # Swapped at round 3
            "TSU": "RB" if race_number <= 2 else "Red Bull",  # Swapped at round 3
            "HAM": "Ferrari", "LEC": "Ferrari",
            "RUS": "Mercedes", "ANT": "Mercedes",
            "NOR": "McLaren", "PIA": "McLaren",
            "ALO": "Aston Martin", "STR": "Aston Martin",
            "GAS": "Alpine",
            "DOO": "Alpine" if race_number <= 6 else None,  # First 6 races
            "COL": "Alpine" if race_number >= 7 else None,  # From Imola (round 7)
            "ALB": "Williams", "SAI": "Williams",
            "BEA": "Haas", "OCO": "Haas",
            "HUL": "Sauber", "BOR": "Sauber",
            "HAD": "RB",  # Full season
        }
        return teams_2025.get(driver_code, "Unknown Team")
    
    return "Unknown Team"

def get_driver_from_number(driver_number: int) -> str:
    if driver_number not in driver_to_number.values() and driver_number == 38 or driver_number not in driver_to_number.values() and driver_number == 50:
        return "BEA"
    
    if driver_number not in driver_to_number.values() and driver_number == 61:
        return "DOO"
    
    for driver, number in driver_to_number.items():
        if number == driver_number:
            return driver
    return "Unknown"

columns = [
    "season", "race_name", "team", "driver",
    "lap_number", "stint_index", 
    # "compound",
    "lap_time",
    "track_status",

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
    #compound: str
    lap_time: float  # collected
    track_status: str

    interval_to_car_ahead: Optional[float]  # seconds, NaN if none
    in_traffic: bool
    
    
class LapDataLoader:
    """
    Collecting per lap metrics for F1 races in the 2025 Season
    """
    
    
    def __init__(self, cache_dir= "fastf1_cache", traffic_interval_threshold=3.0) -> None:
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            print(f"Created cache directory: {cache_dir}")
        
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
        time.sleep(10)
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
        return int(row["stint_number"]) 
    #str(row["compound"])

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

        in_traffic = 0 < gap < self.traffic_interval_threshold # first place is assigned 0 seconds behind the lead
        return gap, in_traffic
    
    def _get_track_status_for_time(self, track_status_df: pd.DataFrame, session_start: Optional[pd.Timestamp], lap_time: pd.Timestamp) -> str:
        if track_status_df.empty or session_start is None:
            return "Green Flag"  # Assume green at start
        
        # Check if required columns exist
        if 'Time' not in track_status_df.columns or 'Status' not in track_status_df.columns:
            return "Green Flag"  # Changed from "Unknown"
        
        # Ensure both timestamps are timezone-aware and in UTC
        if session_start.tz is None:
            session_start = session_start.tz_localize('UTC')
        else:
            session_start = session_start.tz_convert('UTC')
        
        if lap_time.tz is None:
            lap_time = lap_time.tz_localize('UTC')
        else:
            lap_time = lap_time.tz_convert('UTC')
        
        # Convert track_status Time (timedelta) to Timestamps by adding session start time
        track_status_times = session_start + track_status_df['Time']
        
        # Find the most recent track status before this lap time
        mask = track_status_times <= lap_time
        if not mask.any():
            return "Green Flag"  # Changed from "Unknown" - assume green before first status change
        
        status_code = track_status_df[mask].iloc[-1]['Status']
        
        status_map = {
            1: "Green Flag",
            2: "Yellow Flag",
            3: "Safety Car Ending",
            4: "Safety Car",
            5: "Red Flag",
            6: "Virtual Safety Car Deployed",
            7: "Virtual Safety Car Ending",
            '1': "Green Flag",
            '2': "Yellow Flag",
            '3': "Safety Car Ending",
            '4': "Safety Car",
            '5': "Red Flag",
            '6': "Virtual Safety Car Deployed",
            '7': "Virtual Safety Car Ending"
        }
        
        return status_map.get(status_code, "Unknown")
    
    def collect_session_lap_data(self, season, meeting_key, race_index, session_key="R") -> pd.DataFrame:

        race_name = self._get_race_name(meeting_key)
        
        # Load session once and cache track status data
        session_start = None
        try:
            session = fastf1.get_session(season, race_name, "R")
            session.load()
            track_status_df = session.track_status
            
            # Ensure session_start is timezone-aware and in UTC
            session_start = session.date
            if session_start.tz is None:
                session_start = session_start.tz_localize('UTC')
            else:
                session_start = session_start.tz_convert('UTC')
        except Exception as e:
            print(f"  Warning: Could not load track status data: {e}")
            track_status_df = pd.DataFrame()
        
        drivers = self._fetch_df("drivers", session_key=session_key)
        laps = self._fetch_df("laps", session_key=session_key)
        stints = self._fetch_df("stints", session_key=session_key)
        intervals = self._fetch_df("intervals", session_key=session_key)

        
        if not laps.empty:
            laps["date_start"] = pd.to_datetime(laps["date_start"], format='mixed', utc=True)
            
        if not intervals.empty:
            intervals["date"] = pd.to_datetime(intervals["date"], format='mixed', utc=True)

        
        records: List[LapRecord] = []
        
        for driver_number in laps['driver_number'].unique():
            # now we are storing the data for each drivers laps
            driver_laps = laps[laps['driver_number'] == driver_number].copy()
            
            driver_code = get_driver_from_number(driver_number) 
            team_name = get_team_from_driver(driver_code, race_number=race_index, season=season)
            driver_name = driver_code
            
            
            for _, lap in driver_laps.iterrows():
                lap_duration = lap["lap_duration"]  # seconds (float)

                if pd.isna(lap_duration):
                    continue

                lap_number = int(lap["lap_number"])
                lap_time_sec = float(lap_duration)
                
                # Get track status for this specific lap time
                track_status = self._get_track_status_for_time(track_status_df, session_start, lap["date_start"])

                # the stint / compound this lap is on
               
                stint_index = self._find_stint_for_lap(stints, driver_number, lap_number)

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
                    # compound=compound,
                    lap_time=lap_time_sec,
                    track_status=track_status,
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
      
def main(end_race_name: Optional[str] = "Las Vegas") -> pd.DataFrame:
    """
    Collect all race data from 2024 up until a specified race in 2025.
    """
    loader = LapDataLoader()
    all_data = []
    
    # Get all meetings for 2024 and 2025
    for year in [2024, 2025]:
        print(f"\nCollecting {year} season data...")
        
        # Fetch all meetings for the year
        meetings_url = f"{BASE_URL}/meetings"
        response = requests.get(meetings_url, params={"year": year}, timeout=10)
        response.raise_for_status()
        meetings = response.json()
        
        race_index = 1
        
        for meeting in meetings:
            circuit_name = meeting["circuit_short_name"]
            meeting_key = meeting["meeting_key"]
            
            print(f"Processing: {circuit_name} (meeting_key={meeting_key})")
            
            # Get the race session for this meeting
            sessions_url = f"{BASE_URL}/sessions"
            session_response = requests.get(
                sessions_url,
                params={"meeting_key": meeting_key, "session_name": "Race"},
                timeout=10
            )
            session_response.raise_for_status()
            sessions = session_response.json()
            
            if not sessions:
                print(f"  No race session found for {circuit_name}, skipping...")
                continue
            
            session_key = sessions[0]["session_key"]
            
            # Collect lap data for this race
            try:
                race_data = loader.collect_session_lap_data(
                    season=year,
                    meeting_key=meeting_key,
                    session_key=session_key,
                    race_index=race_index
                )
                
                race_index += 1
                
                time.sleep(1)
                
                if not race_data.empty:
                    all_data.append(race_data)
                    print(f"  Collected {len(race_data)} laps")
                else:
                    print(f"  No lap data available")
                    
            except Exception as e:
                print(f"  Error collecting data: {e}")
                continue
            
            # Stop if we've reached the target race in 2025
            if year == 2025 and end_race_name and circuit_name == end_race_name:
                print(f"\nReached {end_race_name} in 2025. Stopping collection.")
                break
        
        # If we stopped mid-2025, don't continue
        if year == 2025 and end_race_name and any(
            meeting["circuit_short_name"] == end_race_name for meeting in meetings
        ):
            break
    
    # Combine all race data
    if all_data:
        combined_df = pd.concat(all_data, ignore_index=True)
        print(f"\nCollection complete: {len(combined_df)} total laps from {len(all_data)} races")
        return combined_df
    else:
        print("\nNo data collected")
        return pd.DataFrame()


if __name__ == "__main__":
    # Example usage: Collect data up to Qatar 2025
    df = main(end_race_name="Lusail")
    
    # Save to CSV
    if not df.empty:
        df.to_csv("f1_race_data_2024_2025.csv", index=False)
        print(f"\nData saved to f1_race_data_2024_2025.csv")
        
        # Display summary
        print("\nData Summary:")
        print(f"Seasons: {df['season'].unique()}")
        print(f"Races: {df['race_name'].nunique()}")
        print(f"Teams: {df['team'].nunique()}")
        print(f"Drivers: {df['driver'].nunique()}")  

# if __name__ == "__main__":
#     # Test track status for a single race
#     loader = LapDataLoader()
    
#     # Test parameters
#     test_year = 2024
#     test_race = "Imola"
    
#     print(f"\nTesting track status collection for {test_year} {test_race}...")
    
#     # Get the meeting key for this race
#     meetings_url = f"{BASE_URL}/meetings"
#     response = requests.get(meetings_url, params={"year": test_year}, timeout=10)
#     response.raise_for_status()
#     meetings = response.json()
    
#     # Find the specific race
#     meeting_key = None
#     for meeting in meetings:
#         if meeting["circuit_short_name"] == test_race:
#             meeting_key = meeting["meeting_key"]
#             print(f"Found meeting_key: {meeting_key}")
#             break
    
#     if meeting_key:
#         # Get session key
#         sessions_url = f"{BASE_URL}/sessions"
#         session_response = requests.get(
#             sessions_url,
#             params={"meeting_key": meeting_key},
#             timeout=10
#         )
#         sessions = session_response.json()
        
#         print(f"\nAvailable sessions:")
#         for session in sessions:
#             print(f"  - {session.get('session_name')} (key: {session.get('session_key')})")
        
#         # Find the race session
#         race_session = None
#         for session in sessions:
#             if session.get('session_name') == 'Race':
#                 race_session = session
#                 break
        
#         if race_session:
#             session_key = race_session["session_key"]
#             print(f"\nUsing Race session_key: {session_key}")
            
#             # Collect data for this race
#             df = loader.collect_session_lap_data(
#                 season=test_year,
#                 meeting_key=meeting_key,
#                 session_key=session_key,
#                 race_index=1
#             )
            
#             # Display results
#             print(f"\nCollected {len(df)} laps")
#             print(f"\nTrack status distribution:")
#             print(df['track_status'].value_counts())
            
#             # Show some sample rows
#             print(f"\nSample data:")
#             pd.set_option('display.max_columns', None)
#             print(df.head(10))
#         else:
#             print(f"No Race session found. Available sessions listed above.")
#     else:
#         print(f"Could not find race: {test_race}")
#         print(f"\nAvailable circuits in {test_year}:")
#         for meeting in meetings:
#             print(f"  - {meeting['circuit_short_name']}")
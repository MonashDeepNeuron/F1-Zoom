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

# data frame columns

# we would have 1 row for:
    # each driver
    # each race
    # each stint 

# from this we are going to calculate:
    # tyre degredation per compound
    # stint length
    # throttle %
    # max / avg speed
    # min corner speeds
    # drop off (third lap pace - final lap pace) - tyres take time to warm up
    # 
columns = [
    "season", "race_name", "round", "circuit_type",
    "team", "driver", "stint_index", "compound",
    "start_lap", "end_lap", "stint_length_laps",

    # Pace
    "avg_laptime", "best_laptime",
    "delta_laptime_first_to_last", "laptime_slope_per_lap",

    # Telemetry-based
    "avg_throttle_pct", "avg_speed", "max_speed",
    "min_corner_speed",

    # Tyre/usage
    "compound",
    "pit_ended_stint",
    
    # traffic
    "laps_in_trffic",
    "traffic_lap_pct", # boolean
    "avg_interval_to_car_ahead", # seconds
    "clean_air_avg_laptime"
]


class carStintLoader:
    
    def __init__(self, cache_dir= "fastf1_cache", traffic_interval_threshold=3.0) -> None:
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            print(f"Created cache directory: {cache_dir}")
        
        fastf1.Cache.enable_cache(cache_dir)
        self.traffic_interval_threshold = traffic_interval_threshold
    
    
    def _map_circuit_to_type(self, circuit_name: str) -> str:
        """returns "Street" or "Permanent" """
        return {
            "Sakhir" : "Street",
            "Jeddah" : "Street",
            "Melbourne" : "Street",
            "Suzuka" : "Permanent",
            "Shanghai" : "Permanent",
            "Miami" : "Street",
            "Imola" : "Permanent",
            "Monte Carlo" : "Street",
            "Montreal" : "Street",
            "Catalunya" : "Permanent",
            "Spielberg" : "Permanent",
            "Silverstone" : "Permanent",
            "Hungaroring" : "Permanent",
            "Spa-Francorchamps" : "Permanent",
            "Zandvoort" : "Permanent",
            "Monza" : "Permanent",
            "Baku" : "Street",
            "Singapore" : "Street",
            "Austin" : "Permanent",
            "Mexico City" : "Permanent",
            "Interlagos" : "Permanent",
            "Jeddah" : "Street",
            "lusail" : "Street",
        }
    
    def load_lap_csv(self, csv_path: str) -> pd.DataFrame:
        df = pd.read_csv(csv_path)
        print(f"Loaded {len(df)} laps from CSV")
        return df
    
    def _get_session(self, season: int, race_name: str):

        try:
            # Get the event by location/circuit name
            session = fastf1.get_session(season, race_name, 'R')
            session.load()
            return session
        
        except Exception as e:
            print(f"Error loading session {season} {race_name}: {e}")
            return None
    
    def calculate_pace_metrics(self, stint_laps: pd.DataFrame) -> dict:
        
        
        # in the case that the stint didn't exist
        if len(stint_laps) == 0:
            return {
                "avg_laptime": np.nan,
                "best_laptime": np.nan,
                "delta_laptime_first_to_last": np.nan,
                "laptime_slope_per_lap": np.nan
            }
        
        valid_laps = stint_laps[stint_laps['lap_time'].notna()].copy()
        
        lap_times = valid_laps['lap_time'].values
        
        avg_laptime = np.mean(lap_times)
        best_laptime_index = np.argmin(lap_times)
        best_laptime = lap_times[best_laptime_index]

        # calculate the difference between first and last lap
        # calculate how much lap time reduced by over the entire stint
        if len(lap_times) >= 2:
            delta_first_to_last = lap_times[-1] - lap_times[0]
            
            # Calculate slope (degradation rate per lap)
            lap_indices = np.arange(len(lap_times)) # creates evenly spaced indicies the same length as the number of lap times
            if len(lap_indices) > 1:
                coeffs = np.polyfit(lap_indices, lap_times, 1) # fitting the lap time fall of to a kine (1 degree polynomial)
                laptime_slope = coeffs[0]  # seconds per lap
            else:
                laptime_slope = 0.0
        else:
            delta_first_to_last = 0.0
            laptime_slope = 0.0
        
        return {
            'avg_laptime': avg_laptime,
            'best_laptime': best_laptime,
            'delta_laptime_first_to_last': delta_first_to_last,
            'laptime_slope_per_lap': laptime_slope,
        }
    
    
    def _calculate_traffic_metrics(self, stint_laps: pd.DataFrame) -> dict:
        
        total_laps = len(stint_laps)
        
        if total_laps == 0:
            return {
                'laps_in_traffic': 0,
                'traffic_lap_pct': 0.0,
                'avg_interval_to_car_ahead': np.nan,
                'clean_air_avg_laptime': np.nan,
            }
        
        if 'in_traffic' in stint_laps.columns:
            laps_in_traffic = stint_laps['in_traffic'].sum()
            traffic_lap_pct = laps_in_traffic / total_laps
        else:
            laps_in_traffic = 0
            traffic_lap_pct = 0.0
        
        if 'interval_to_car_ahead' in stint_laps.columns:
            avg_interval_to_car_ahead = stint_laps['interval_to_car_ahead'].mean()
        else:
            avg_interval_to_car_ahead = np.nan
        
        if 'in_traffic' in stint_laps.columns and 'lap_time' in stint_laps.columns:
            clean_laps = stint_laps[stint_laps['in_traffic'] == False]
            if len(clean_laps) > 0:
                clean_air_avg_laptime = clean_laps['lap_time'].mean()
            else:
                clean_air_avg_laptime = np.nan
        else:
            clean_air_avg_laptime = np.nan
        
        return {
            'laps_in_traffic': int(laps_in_traffic),
            'traffic_lap_pct': traffic_lap_pct,
            'avg_interval_to_car_ahead': avg_interval_to_car_ahead,
            'clean_air_avg_laptime': clean_air_avg_laptime,
        }
    
    def _calculate_telemetry_metrics(self, session, driver: str, lap_numbers: list) -> dict:

        if session is None:
            return {
                'avg_throttle_pct': np.nan,
                'avg_speed': np.nan,
                'max_speed': np.nan,
                'min_corner_speed': np.nan,
            }
        
        try:
            # Get driver's laps
            driver_laps = session.laps.pick_driver(driver)
            stint_driver_laps = driver_laps[driver_laps['LapNumber'].isin(lap_numbers)]
            
            if len(stint_driver_laps) == 0:
                return {
                    'avg_throttle_pct': np.nan,
                    'avg_speed': np.nan,
                    'max_speed': np.nan,
                    'min_corner_speed': np.nan,
                }
            
            # Collect telemetry data across all laps
            all_throttle = []
            all_speed = []
            all_max_speeds = []
            all_min_corner_speeds = []
            
            for lap_num in lap_numbers:
                try:
                    lap = driver_laps[driver_laps['LapNumber'] == lap_num]
                    if len(lap) == 0:
                        continue
                    
                    lap = lap.iloc[0]
                    
                    # Get telemetry for this lap
                    telemetry = lap.get_telemetry()
                    
                    if telemetry is not None and len(telemetry) > 0:
                        # Throttle percentage
                        all_throttle.extend(telemetry['Throttle'].values)
                        
                        # Speed data
                        speeds = telemetry['Speed'].values
                        all_speed.extend(speeds)
                        all_max_speeds.append(np.max(speeds))
                        
                        # Corner speeds (typically where speed < 150 km/h)
                        corner_speeds = speeds[speeds < 150]
                        if len(corner_speeds) > 0:
                            all_min_corner_speeds.append(np.min(corner_speeds))
                
                except Exception as e:
                    # Skip laps with telemetry errors
                    continue
            
            # Calculate aggregated metrics
            if len(all_throttle) > 0:
                avg_throttle_pct = np.mean(all_throttle)
            else:
                avg_throttle_pct = np.nan
            
            if len(all_speed) > 0:
                avg_speed = np.mean(all_speed)
            else:
                avg_speed = np.nan
            
            if len(all_max_speeds) > 0:
                max_speed = np.max(all_max_speeds)
            else:
                max_speed = np.nan
            
            if len(all_min_corner_speeds) > 0:
                min_corner_speed = np.min(all_min_corner_speeds)
            else:
                min_corner_speed = np.nan
            
            return {
                'avg_throttle_pct': avg_throttle_pct,
                'avg_speed': avg_speed,
                'max_speed': max_speed,
                'min_corner_speed': min_corner_speed,
            }
        
        except Exception as e:
            print(f"Error calculating telemetry for {driver}: {e}")
            return {
                'avg_throttle_pct': np.nan,
                'avg_speed': np.nan,
                'max_speed': np.nan,
                'min_corner_speed': np.nan,
            }
    
    def process_stints(self, csv_path: str, include_telemetry: bool = True, 
                      seasons: Optional[list] = None) -> pd.DataFrame:
        # Load lap data
        lap_data = self.load_lap_csv(csv_path)
        
        # Filter seasons if specified
        if seasons is not None:
            lap_data = lap_data[lap_data['season'].isin(seasons)]
        
        # Group by stint
        stint_groups = lap_data.groupby(['season', 'race_name', 'team', 'driver', 'stint_index'])
        
        stint_records = []
        sessions_cache = {}  # Cache sessions to avoid reloading
        
        total_stints = len(stint_groups)
        print(f"Processing {total_stints} stints...")
        
        for idx, ((season, race_name, team, driver, stint_index), stint_laps) in enumerate(stint_groups):
            print(f"[{idx+1}/{total_stints}] {season} {race_name} - {driver} Stint {stint_index}")
            
            # Basic stint information
            compound = stint_laps['compound'].iloc[0]
            start_lap = int(stint_laps['lap_number'].min())
            end_lap = int(stint_laps['lap_number'].max())
            stint_length_laps = len(stint_laps)
            
            # Determine if stint ended with a pit stop
            # Check if there's a next stint for this driver in this race
            next_stint_exists = len(lap_data[
                (lap_data['season'] == season) &
                (lap_data['race_name'] == race_name) &
                (lap_data['driver'] == driver) &
                (lap_data['stint_index'] == stint_index + 1)
            ]) > 0
            pit_ended_stint = next_stint_exists
            
            # Get circuit type
            circuit_type = self._map_circuit_to_type(race_name)
            
            # Get round number (FastF1 uses round numbers)
            session_key = (season, race_name)
            if session_key not in sessions_cache:
                sessions_cache[session_key] = self._get_session(season, race_name)
            
            session = sessions_cache[session_key]
            
            # Determine round number
            if session is not None:
                try:
                    round_num = session.event['RoundNumber']
                except:
                    round_num = 0
            else:
                round_num = 0
            
            # Calculate pace metrics
            pace_metrics = self._calculate_pace_metrics(stint_laps)
            
            # Calculate traffic metrics
            traffic_metrics = self._calculate_traffic_metrics(stint_laps)
            
            # Calculate telemetry metrics
            if include_telemetry:
                lap_numbers = stint_laps['lap_number'].tolist()
                telemetry_metrics = self._calculate_telemetry_metrics(session, driver, lap_numbers)
            else:
                telemetry_metrics = {
                    'avg_throttle_pct': np.nan,
                    'avg_speed': np.nan,
                    'max_speed': np.nan,
                    'min_corner_speed': np.nan,
                }
            
            # Build stint record
            stint_record = {
                'season': season,
                'race_name': race_name,
                'round': round_num,
                'circuit_type': circuit_type,
                'team': team,
                'driver': driver,
                'stint_index': stint_index,
                'compound': compound,
                'start_lap': start_lap,
                'end_lap': end_lap,
                'stint_length_laps': stint_length_laps,
                'pit_ended_stint': pit_ended_stint,
            }
            
            # Add calculated metrics
            stint_record.update(pace_metrics)
            stint_record.update(telemetry_metrics)
            stint_record.update(traffic_metrics)
            
            stint_records.append(stint_record)
        
        # Convert to DataFrame
        stint_df = pd.DataFrame(stint_records)
        
        print(f"\nCompleted! Processed {len(stint_df)} stints.")
        return stint_df


# Example usage
if __name__ == "__main__":
    # Initialize loader
    loader = carStintLoader(cache_dir="fastf1_cache", traffic_interval_threshold=3.0)
    
    # Process stints from CSV
    stint_data = loader.process_stints(
        csv_path='lap_data.csv',
        include_telemetry=True,  # Set to False for faster processing without telemetry
        seasons=[2024]  # Process only 2024, or None for all seasons
    )
    
    # Save results
    stint_data.to_csv('stint_analysis.csv', index=False)
    
    # Display summary
    print("\n=== Stint Data Summary ===")
    print(f"Total stints: {len(stint_data)}")
    print(f"\nColumns: {list(stint_data.columns)}")
    print(f"\nFirst few rows:")
    print(stint_data.head())
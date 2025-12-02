# one row, per team per race, summarising the driver-lvel stint / lap data

# race pace rank
# qualifying pace rank
# top speed rank
# corner speed rank
# drag index (top_speed_rank - corner_speed_rank)
# circuit type (track vs street)
# avg race pace
# avg stint length

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
from collections import defaultdict

columns = [
    "season", "race_name", "round", "circuit_type",
    "team",

    # Pace
    "avg_race_pace",                 
    "clean_air_avg_race_pace",       # using clean_air_avg_laptime from stints          

    # Speed & Cornering
    "top_speed",                     
    "cornering_speed",               
    "top_speed_rank",                
    "corner_speed_rank",
    "drag_index",                    # top_speed_rank - corner_speed_rank

    # Tyre usage
    "avg_stint_length",              
    "stints_soft",                  
    "stints_medium",
    "stints_hard", 

    # Per-compound degradation (averaged for the race)
    "deg_soft_slope",                # mean laptime_slope_per_lap for SOFT
    "deg_medium_slope",
    "deg_hard_slope",

    # Per-compound drop-off (3rd lap vs last lap)
    "dropoff_soft",
    "dropoff_medium",
    "dropoff_hard",

    # Throttle / PU Behaviour
    "avg_throttle_pct",              # weighted across all stints
    "avg_speed",                     # total race avg speed (from stints)

    # Traffic / Clean Air Behaviour
    "traffic_lap_pct",               
    "avg_interval_to_car_ahead",     
    "clean_air_pace_advantage",      # clean_air_avg_pace - avg_race_pace

    # Reliability
    "mechanical_dnf_count",

    # Pit Crew
    "avg_pitstop_time"
]


class TeamRaceSummaryLoader:
    """
    Create team-level race summaries from stint data and FastF1 session data.
    """
    
    def __init__(self, cache_dir="fastf1_cache"):
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            print(f"Created cache directory: {cache_dir}")
        
        fastf1.Cache.enable_cache(cache_dir)
        self.circuit_type_map = self._build_circuit_type_map()
    
    def _build_circuit_type_map(self) -> Dict[str, str]:
        """Map circuit names to types."""
        return {
            "Sakhir": "Permanent",
            "Jeddah": "Street",
            "Melbourne": "Street",
            "Suzuka": "Permanent",
            "Shanghai": "Permanent",
            "Miami": "Street",
            "Imola": "Permanent",
            "Monte Carlo": "Street",
            "Montreal": "Street",
            "Catalunya": "Permanent",
            "Spielberg": "Permanent",
            "Silverstone": "Permanent",
            "Hungaroring": "Permanent",
            "Spa-Francorchamps": "Permanent",
            "Zandvoort": "Permanent",
            "Monza": "Permanent",
            "Baku": "Street",
            "Singapore": "Street",
            "Austin": "Permanent",
            "Mexico City": "Permanent",
            "Interlagos": "Permanent",
            "Las Vegas": "Street",
            "Lusail": "Permanent",
            "Yas Marina": "Permanent",
        }
    
    
    def load_stint_data(self, csv_path: str) -> pd.DataFrame:
        return pd.read_csv(csv_path)
    
    def _get_session(self, season: int, race_name: str, session_type: str = 'R'):
        try:
            session = fastf1.get_session(season, race_name, session_type)
            session.load()
            return session
        except Exception as e:
            print(f"Error loading {session_type} session for {season} {race_name}: {e}")
            return None
    
    def _calculate_pace_metrics(self, team_stints: pd.DataFrame) -> Dict:
        metrics = {}
        
        # Average race pace (weighted by stint length)
        if 'avg_laptime' in team_stints.columns and 'stint_length_laps' in team_stints.columns:
            total_laps = team_stints['stint_length_laps'].sum()
            if total_laps > 0:
                weighted_pace = (team_stints['avg_laptime'] * team_stints['stint_length_laps']).sum()
                metrics['avg_race_pace'] = weighted_pace / total_laps
            else:
                metrics['avg_race_pace'] = np.nan
        else:
            metrics['avg_race_pace'] = np.nan
        
        
        
        # Clean air average race pace
        if 'clean_air_avg_laptime' in team_stints.columns and 'stint_length_laps' in team_stints.columns:
            clean_stints = team_stints[team_stints['clean_air_avg_laptime'].notna()]
            if len(clean_stints) > 0:
                total_clean_laps = clean_stints['stint_length_laps'].sum()
                if total_clean_laps > 0:
                    weighted_clean_pace = (clean_stints['clean_air_avg_laptime'] * 
                                          clean_stints['stint_length_laps']).sum()
                    metrics['clean_air_avg_race_pace'] = weighted_clean_pace / total_clean_laps
                else:
                    metrics['clean_air_avg_race_pace'] = np.nan
            else:
                metrics['clean_air_avg_race_pace'] = np.nan
        else:
            metrics['clean_air_avg_race_pace'] = np.nan
        
        return metrics
    
    
    
    def _calculate_speed_metrics(self, team_stints: pd.DataFrame) -> Dict:
        metrics = {}
        
        # Top speed (max across all stints)
        if 'max_speed' in team_stints.columns:
            metrics['top_speed'] = team_stints['max_speed'].max()
        else:
            metrics['top_speed'] = np.nan
        
        # Cornering speed (average of minimum corner speeds)
        if 'min_corner_speed' in team_stints.columns:
            valid_corner_speeds = team_stints['min_corner_speed'].dropna()
            if len(valid_corner_speeds) > 0:
                metrics['cornering_speed'] = valid_corner_speeds.mean()
            else:
                metrics['cornering_speed'] = np.nan
        else:
            metrics['cornering_speed'] = np.nan
        
        # Rankings will be calculated later across all teams
        metrics['top_speed_rank'] = np.nan
        metrics['corner_speed_rank'] = np.nan
        metrics['drag_index'] = np.nan
        
        return metrics
    
    def _calculate_tyre_metrics(self, team_stints: pd.DataFrame) -> Dict:
        metrics = {}
        
        # Average stint length
        if 'stint_length_laps' in team_stints.columns:
            metrics['avg_stint_length'] = team_stints['stint_length_laps'].mean()
        else:
            metrics['avg_stint_length'] = np.nan
        
        # Count stints by compound
        if 'compound' in team_stints.columns:
            compound_counts = team_stints['compound'].value_counts()
            metrics['stints_soft'] = compound_counts.get('SOFT', 0)
            metrics['stints_medium'] = compound_counts.get('MEDIUM', 0)
            metrics['stints_hard'] = compound_counts.get('HARD', 0)
        else:
            metrics['stints_soft'] = 0
            metrics['stints_medium'] = 0
            metrics['stints_hard'] = 0
        
        # Degradation slopes per compound
        for compound in ['SOFT', 'MEDIUM', 'HARD']:
            col_name = f'deg_{compound.lower()}_slope'
            if 'compound' in team_stints.columns and 'laptime_slope_per_lap' in team_stints.columns:
                compound_stints = team_stints[team_stints['compound'] == compound]
                if len(compound_stints) > 0:
                    metrics[col_name] = compound_stints['laptime_slope_per_lap'].mean()
                else:
                    metrics[col_name] = np.nan
            else:
                metrics[col_name] = np.nan
        
        # Drop-off per compound (delta from first to last lap)
        for compound in ['SOFT', 'MEDIUM', 'HARD']:
            col_name = f'dropoff_{compound.lower()}'
            if 'compound' in team_stints.columns and 'delta_laptime_first_to_last' in team_stints.columns:
                compound_stints = team_stints[team_stints['compound'] == compound]
                if len(compound_stints) > 0:
                    metrics[col_name] = compound_stints['delta_laptime_first_to_last'].mean()
                else:
                    metrics[col_name] = np.nan
            else:
                metrics[col_name] = np.nan
        
        return metrics
    
    def _calculate_pu_metrics(self, team_stints: pd.DataFrame) -> Dict:
        metrics = {}
        
        # Weighted average throttle percentage
        if 'avg_throttle_pct' in team_stints.columns and 'stint_length_laps' in team_stints.columns:
            valid_stints = team_stints[team_stints['avg_throttle_pct'].notna()]
            if len(valid_stints) > 0:
                total_laps = valid_stints['stint_length_laps'].sum()
                if total_laps > 0:
                    weighted_throttle = (valid_stints['avg_throttle_pct'] * 
                                        valid_stints['stint_length_laps']).sum()
                    metrics['avg_throttle_pct'] = weighted_throttle / total_laps
                else:
                    metrics['avg_throttle_pct'] = np.nan
            else:
                metrics['avg_throttle_pct'] = np.nan
        else:
            metrics['avg_throttle_pct'] = np.nan
        
        # Weighted average speed
        if 'avg_speed' in team_stints.columns and 'stint_length_laps' in team_stints.columns:
            valid_stints = team_stints[team_stints['avg_speed'].notna()]
            if len(valid_stints) > 0:
                total_laps = valid_stints['stint_length_laps'].sum()
                if total_laps > 0:
                    weighted_speed = (valid_stints['avg_speed'] * 
                                     valid_stints['stint_length_laps']).sum()
                    metrics['avg_speed'] = weighted_speed / total_laps
                else:
                    metrics['avg_speed'] = np.nan
            else:
                metrics['avg_speed'] = np.nan
        else:
            metrics['avg_speed'] = np.nan
        
        return metrics
    
    
    def _calculate_traffic_metrics(self, team_stints: pd.DataFrame) -> Dict:
        """Calculate traffic and clean air metrics."""
        metrics = {}
        
        # Traffic lap percentage (weighted)
        if 'traffic_lap_pct' in team_stints.columns and 'stint_length_laps' in team_stints.columns:
            total_laps = team_stints['stint_length_laps'].sum()
            if total_laps > 0:
                weighted_traffic = (team_stints['traffic_lap_pct'] * 
                                   team_stints['stint_length_laps']).sum()
                metrics['traffic_lap_pct'] = weighted_traffic / total_laps
            else:
                metrics['traffic_lap_pct'] = np.nan
        else:
            metrics['traffic_lap_pct'] = np.nan
        
        # Average interval to car ahead
        if 'avg_interval_to_car_ahead' in team_stints.columns:
            valid_intervals = team_stints['avg_interval_to_car_ahead'].dropna()
            if len(valid_intervals) > 0:
                metrics['avg_interval_to_car_ahead'] = valid_intervals.mean()
            else:
                metrics['avg_interval_to_car_ahead'] = np.nan
        else:
            metrics['avg_interval_to_car_ahead'] = np.nan
        
        # Clean air pace advantage
        if 'avg_race_pace' in metrics and 'clean_air_avg_race_pace' in metrics:
            if not np.isnan(metrics['clean_air_avg_race_pace']) and not np.isnan(metrics['avg_race_pace']):
                # Note: clean air should be faster (lower time), so this will be negative
                metrics['clean_air_pace_advantage'] = (metrics['clean_air_avg_race_pace'] - 
                                                       metrics['avg_race_pace'])
            else:
                metrics['clean_air_pace_advantage'] = np.nan
        else:
            metrics['clean_air_pace_advantage'] = np.nan
        
        return metrics
# one row, per driver per race, summarising the driver-level stint / lap data

# race pace rank
# qualifying pace rank
# top speed rank
# corner speed rank
# drag index (top_speed_rank - corner_speed_rank)
# circuit type (track vs street)
# avg race pace
# avg stint length

from __future__ import annotations

import fastf1
import os
import pandas as pd
import numpy as np
import requests
from dataclasses import dataclass
from typing import List, Optional, Dict
from datetime import timedelta
import time
from collections import defaultdict

columns = [
    "season", "driver", "race_name", "round", "circuit_type",
    "team",

    # Race Result
    "finishing_position",            # Final classified position
    "race_status",                   # 'Finished', '+1 Lap', 'Crash', 'Gearbox', etc.

    # Pace
    "avg_race_pace",                 
    "clean_air_avg_race_pace",       # using clean_air_avg_laptime from stints
    "grid_avg_race_pace",
    "pace_delta_to_grid",
    "pace_zscore_vs_grid",
    "pace_score_vs_grid",
    "pace_score_0_100",          

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
    # "mechanical_dnf_count", move to season summary

    # Pit Crew
    # "avg_pitstop_time", move to season summary
]


class TeamRaceSummaryLoader:
    """
    Create driver-level race summaries from stint data and FastF1 session data.
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
    
    def _get_race_results(self, season: int, race_name: str) -> Dict[str, Dict]:
        """
        Get finishing positions and race status for all drivers in a race.
        
        Returns:
            Dict mapping driver abbreviation to {'position': int, 'status': str}
        """
        results_dict = {}
        try:
            session = fastf1.get_session(season, race_name, 'R')
            session.load()
            results = session.results
            
            for idx, row in results.iterrows():
                driver_code = row['Abbreviation']
                position = int(row['Position']) if pd.notna(row['Position']) else np.nan
                status = row['Status'] if pd.notna(row.get('Status')) else np.nan
                results_dict[driver_code] = {
                    'position': position,
                    'status': status
                }
                
        except Exception as e:
            print(f"Error loading race results for {season} {race_name}: {e}")
        
        return results_dict
    
    def _calculate_pace_metrics(self, driver_stints: pd.DataFrame) -> Dict:
        metrics = {}
        
        # Average race pace (weighted by stint length)
        if 'avg_laptime' in driver_stints.columns and 'stint_length_laps' in driver_stints.columns:
            total_laps = driver_stints['stint_length_laps'].sum()
            if total_laps > 0:
                weighted_pace = (driver_stints['avg_laptime'] * driver_stints['stint_length_laps']).sum()
                metrics['avg_race_pace'] = weighted_pace / total_laps
            else:
                metrics['avg_race_pace'] = np.nan
        else:
            metrics['avg_race_pace'] = np.nan
        
        
        
        # Clean air average race pace
        if 'clean_air_avg_laptime' in driver_stints.columns and 'stint_length_laps' in driver_stints.columns:
            clean_stints = driver_stints[driver_stints['clean_air_avg_laptime'].notna()]
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
    
    
    
    def _calculate_speed_metrics(self, driver_stints: pd.DataFrame) -> Dict:
        metrics = {}
        
        # Top speed (max across all stints)
        if 'max_speed' in driver_stints.columns:
            metrics['top_speed'] = driver_stints['max_speed'].max()
        else:
            metrics['top_speed'] = np.nan
        
        # Cornering speed (average of minimum corner speeds)
        if 'min_corner_speed' in driver_stints.columns:
            valid_corner_speeds = driver_stints['min_corner_speed'].dropna()
            if len(valid_corner_speeds) > 0:
                metrics['cornering_speed'] = valid_corner_speeds.mean()
            else:
                metrics['cornering_speed'] = np.nan
        else:
            metrics['cornering_speed'] = np.nan
        
        # Rankings will be calculated later across all drivers
        metrics['top_speed_rank'] = np.nan
        metrics['corner_speed_rank'] = np.nan
        metrics['drag_index'] = np.nan
        
        return metrics
    
    def _calculate_tyre_metrics(self, driver_stints: pd.DataFrame) -> Dict:
        metrics = {}
        
        # Average stint length
        if 'stint_length_laps' in driver_stints.columns:
            metrics['avg_stint_length'] = driver_stints['stint_length_laps'].mean()
        else:
            metrics['avg_stint_length'] = np.nan
        
        # Count stints by compound
        if 'compound' in driver_stints.columns:
            compound_counts = driver_stints['compound'].value_counts()
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
            if 'compound' in driver_stints.columns and 'laptime_slope_per_lap' in driver_stints.columns:
                compound_stints = driver_stints[driver_stints['compound'] == compound]
                if len(compound_stints) > 0:
                    metrics[col_name] = compound_stints['laptime_slope_per_lap'].mean()
                else:
                    metrics[col_name] = np.nan
            else:
                metrics[col_name] = np.nan
        
        # Drop-off per compound (delta from first to last lap)
        for compound in ['SOFT', 'MEDIUM', 'HARD']:
            col_name = f'dropoff_{compound.lower()}'
            if 'compound' in driver_stints.columns and 'delta_laptime_first_to_last' in driver_stints.columns:
                compound_stints = driver_stints[driver_stints['compound'] == compound]
                if len(compound_stints) > 0:
                    metrics[col_name] = compound_stints['delta_laptime_first_to_last'].mean()
                else:
                    metrics[col_name] = np.nan
            else:
                metrics[col_name] = np.nan
        
        return metrics
    
    def _calculate_pu_metrics(self, driver_stints: pd.DataFrame) -> Dict:
        metrics = {}
        
        # Weighted average throttle percentage
        if 'avg_throttle_pct' in driver_stints.columns and 'stint_length_laps' in driver_stints.columns:
            valid_stints = driver_stints[driver_stints['avg_throttle_pct'].notna()]
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
        if 'avg_speed' in driver_stints.columns and 'stint_length_laps' in driver_stints.columns:
            valid_stints = driver_stints[driver_stints['avg_speed'].notna()]
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
    
    
    def _calculate_traffic_metrics(self, driver_stints: pd.DataFrame) -> Dict:
        """Calculate traffic and clean air metrics."""
        metrics = {}
        
        # Traffic lap percentage (weighted)
        if 'traffic_lap_pct' in driver_stints.columns and 'stint_length_laps' in driver_stints.columns:
            total_laps = driver_stints['stint_length_laps'].sum()
            if total_laps > 0:
                weighted_traffic = (driver_stints['traffic_lap_pct'] * 
                                   driver_stints['stint_length_laps']).sum()
                metrics['traffic_lap_pct'] = weighted_traffic / total_laps
            else:
                metrics['traffic_lap_pct'] = np.nan
        else:
            metrics['traffic_lap_pct'] = np.nan
        
        # Average interval to car ahead
        if 'avg_interval_to_car_ahead' in driver_stints.columns:
            valid_intervals = driver_stints['avg_interval_to_car_ahead'].dropna()
            if len(valid_intervals) > 0:
                metrics['avg_interval_to_car_ahead'] = valid_intervals.mean()
            else:
                metrics['avg_interval_to_car_ahead'] = np.nan
        else:
            metrics['avg_interval_to_car_ahead'] = np.nan
        
        # Clean air pace advantage will be calculated in generate_summary
        # after combining pace and traffic metrics
        metrics['clean_air_pace_advantage'] = np.nan
        
        return metrics
    
    def _calculate_rankings(self, race_summary: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate rankings for top_speed and cornering_speed within each race.
        Rankings are calculated per (season, race_name) group.
        Rank 1 = best (highest value).
        """
        race_summary = race_summary.copy()
        
        # Group by season and race_name to calculate rankings within each race
        for (season, race_name), group in race_summary.groupby(['season', 'race_name']):
            # Top speed ranking (higher is better, rank 1 = highest)
            valid_top_speed = group['top_speed'].notna()
            if valid_top_speed.sum() > 0:
                race_summary.loc[group.index, 'top_speed_rank'] = (
                    group.loc[valid_top_speed, 'top_speed']
                    .rank(ascending=False, method='min')
                    .astype(float)
                )
            
            # Corner speed ranking (higher is better, rank 1 = highest)
            valid_corner_speed = group['cornering_speed'].notna()
            if valid_corner_speed.sum() > 0:
                race_summary.loc[group.index, 'corner_speed_rank'] = (
                    group.loc[valid_corner_speed, 'cornering_speed']
                    .rank(ascending=False, method='min')
                    .astype(float)
                )
            
            # Drag index = top_speed_rank - corner_speed_rank
            # Positive = more drag (high top speed rank but low corner speed rank)
            # Negative = less drag (low top speed rank but high corner speed rank)
            valid_ranks = (
                race_summary.loc[group.index, 'top_speed_rank'].notna() &
                race_summary.loc[group.index, 'corner_speed_rank'].notna()
            )
            if valid_ranks.sum() > 0:
                race_summary.loc[group.index[valid_ranks], 'drag_index'] = (
                    race_summary.loc[group.index[valid_ranks], 'top_speed_rank'] -
                    race_summary.loc[group.index[valid_ranks], 'corner_speed_rank']
                )
        
        return race_summary

    def _add_grid_relative_pace_scores(
        self,
        summary_df: pd.DataFrame,
        pace_col: str = "avg_race_pace",
        group_cols: List[str] = ["season", "race_name"]
    ) -> pd.DataFrame:
        """
        Add grid-relative pace scoring columns.

        Adds:
            - grid_avg_race_pace
            - pace_delta_to_grid
            - pace_zscore_vs_grid
            - pace_score_vs_grid

        Notes:
            - Lower lap time = better
            - pace_score_vs_grid: higher is better
        """
        df = summary_df.copy()

        grp = df.groupby(group_cols)

        # Grid average pace
        df["grid_avg_race_pace"] = grp[pace_col].transform("mean")

        # Delta to grid (seconds)
        df["pace_delta_to_grid"] = df[pace_col] - df["grid_avg_race_pace"]

        # Z-score normalization within race
        grid_std = grp[pace_col].transform("std")
        df["pace_zscore_vs_grid"] = df["pace_delta_to_grid"] / grid_std

        # Higher = better (faster than grid)
        df["pace_score_vs_grid"] = -df["pace_zscore_vs_grid"]

        # Safety: handle zero / missing std
        invalid_std = grid_std.isna() | (grid_std == 0)
        df.loc[invalid_std, ["pace_zscore_vs_grid", "pace_score_vs_grid"]] = np.nan
        
        df["pace_score_0_100"] = grp[pace_col].transform(
            lambda s: 100 * (1 - s.rank(pct=True, ascending=True))
        )

        return df
        
    def generate_summary(self, stint_csv_path: str) -> pd.DataFrame:
        """
        Generate driver-level race summary from stint data.
        
        Args:
            stint_csv_path: Path to stint_analysis.csv
            
        Returns:
            DataFrame with one row per driver per race
        """
        # Load stint data
        print(f"Loading stint data from {stint_csv_path}...")
        stint_df = self.load_stint_data(stint_csv_path)
        print(f"Loaded {len(stint_df)} stint records")
        
        # Pre-fetch race results (finishing positions and status) for all unique races
        print("Fetching race results (positions and status)...")
        race_results_cache = {}
        unique_races = stint_df[['season', 'race_name']].drop_duplicates()
        for _, race in unique_races.iterrows():
            season_val, race_name_val = race['season'], race['race_name']
            race_results_cache[(season_val, race_name_val)] = self._get_race_results(season_val, race_name_val)
        
        # Group by season, race_name, and driver
        summary_records = []
        
        for (season, race_name, driver), driver_stints in stint_df.groupby(['season', 'race_name', 'driver']):
            # Get metadata from first row (should be same for all rows in group)
            first_row = driver_stints.iloc[0]
            round_num = first_row.get('round', np.nan)
            circuit_type = first_row.get('circuit_type', np.nan)
            team = first_row.get('team', np.nan)
            
            # Get finishing position and race status
            driver_result = race_results_cache.get((season, race_name), {}).get(driver, {})
            finishing_position = driver_result.get('position', np.nan)
            race_status = driver_result.get('status', np.nan)
            
            # Calculate all metrics
            pace_metrics = self._calculate_pace_metrics(driver_stints)
            speed_metrics = self._calculate_speed_metrics(driver_stints)
            tyre_metrics = self._calculate_tyre_metrics(driver_stints)
            pu_metrics = self._calculate_pu_metrics(driver_stints)
            
            # Traffic metrics
            traffic_metrics = self._calculate_traffic_metrics(driver_stints)
            
            # Calculate clean_air_pace_advantage (requires both pace and traffic metrics)
            if not np.isnan(pace_metrics.get('clean_air_avg_race_pace', np.nan)) and \
               not np.isnan(pace_metrics.get('avg_race_pace', np.nan)):
                # Note: clean air should be faster (lower time), so this will be negative
                traffic_metrics['clean_air_pace_advantage'] = (
                    pace_metrics['clean_air_avg_race_pace'] - 
                    pace_metrics['avg_race_pace']
                )
            else:
                traffic_metrics['clean_air_pace_advantage'] = np.nan
            
            # Combine all metrics
            record = {
                'season': season,
                'driver': driver,
                'race_name': race_name,
                'round': round_num,
                'circuit_type': circuit_type,
                'team': team,
                'finishing_position': finishing_position,
                'race_status': race_status,
                **pace_metrics,
                **speed_metrics,
                **tyre_metrics,
                **pu_metrics,
                **traffic_metrics
            }
            
            summary_records.append(record)
        
        # Create DataFrame
        summary_df = pd.DataFrame(summary_records)
        
        summary_df = self._add_grid_relative_pace_scores(summary_df)
        
        # Calculate rankings
        print("Calculating rankings...")
        summary_df = self._calculate_rankings(summary_df)
    
        # Ensure all columns from the columns list are present
        for col in columns:
            if col not in summary_df.columns:
                summary_df[col] = np.nan
        
        # Reorder columns to match the defined order
        summary_df = summary_df[columns]
        
        # Sort by season, round, driver for consistency
        summary_df = summary_df.sort_values(['season', 'round', 'driver']).reset_index(drop=True)
        
        print(f"Generated summary with {len(summary_df)} driver-race records")
        return summary_df
    
    def save_summary(self, summary_df: pd.DataFrame, output_path: str):
        """Save summary DataFrame to CSV."""
        summary_df.to_csv(output_path, index=False)
        print(f"Saved summary to {output_path}")


def main(stint_csv_path: str = "stint_analysis.csv", 
         output_csv_path: str = "car_race_summary.csv",
         cache_dir: str = "fastf1_cache"):
    """
    Main function to generate driver race summary.
    
    Args:
        stint_csv_path: Path to input stint_analysis.csv
        output_csv_path: Path to output car_race_summary.csv
        cache_dir: Directory for FastF1 cache
    """
    loader = TeamRaceSummaryLoader(cache_dir=cache_dir)
    summary_df = loader.generate_summary(stint_csv_path)
    loader.save_summary(summary_df, output_csv_path)
    return summary_df


if __name__ == "__main__":
    import sys
    
    # Allow command line arguments
    stint_path = sys.argv[1] if len(sys.argv) > 1 else "Car_Tyre_CSV/stint_analysis.csv"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "Car_Tyre_CSV/car_race_summary.csv"
    
    main(stint_csv_path="Car_Tyre_CSV/stint_analysis.csv", output_csv_path="Car_Tyre_CSV/driver_race_summary.csv")
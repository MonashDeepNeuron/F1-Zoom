# Extract driver positions from FP1, FP2, FP3, Qualifying, Sprint Qualifying, Sprint Race, and Race sessions
# Apply weights and calculate weighted performance scores for Monte Carlo simulation

from __future__ import annotations

import fastf1
import os
import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
import time

# Define column order for output CSV
columns = [
    # Metadata
    "season", "driver", "race_name", "round", "circuit_type", "team",
    
    # Positions
    "fp1_pos", "fp2_pos", "fp3_pos", 
    "sprint_qualifying_pos", "sprint_race_pos",
    "qualifying_pos", "race_pos",
    
    # DNF Information
    "race_dnf_status",  # e.g., "Crash", "Gearbox", "Engine"
    "race_classified_position",  # e.g., "R", "D", or numeric position
    
    # Weighted score
    "weighted_performance_score",
]

# Session weights
WEIGHTS_STANDARD = {
    'FP1': 0.1,
    'FP2': 0.2,
    'FP3': 0.4,
    'Qualifying': 0.8,
    'Race': 1.0,
}

WEIGHTS_SPRINT = {
    'FP1': 0.1,  # least weight
    'Sprint Qualifying': 0.3,
    'Sprint Race': 0.6,
    'Qualifying': 0.8,
    'Race': 1.0,  # most weight
}


class QualifyingToRacePerformance:
    """
    Extract driver positions from practice, qualifying, and race sessions.
    Apply weights and calculate weighted performance scores.
    """
    
    def __init__(self, cache_dir="fastf1_cache"):
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
            print(f"Created cache directory: {cache_dir}")
        
        fastf1.Cache.enable_cache(cache_dir)
        self.cache_dir = cache_dir
    
    def load_race_summary(self, csv_path: str = "car_race_summary.csv") -> pd.DataFrame:
        """Load race summary CSV to get unique races and drivers."""
        return pd.read_csv(csv_path)
    
    def _normalize_race_name(self, race_name: str) -> str:
        """
        Normalize race names to match FastF1's expected format.
        
        Args:
            race_name: Race name from CSV
            
        Returns:
            Normalized race name for FastF1
        """
        # Mapping of CSV race names to FastF1 race names
        name_mapping = {
            "Yas Marina Circuit": "Yas Marina",
            "Singapore Grand Prix": "Singapore",
            # Add other mappings as needed if more discrepancies are found
        }
        
        return name_mapping.get(race_name, race_name)
    
    def _get_session(self, season: int, race_name: str, session_type: str):
        """
        Load a FastF1 session.
        
        Args:
            season: Season year
            race_name: Race name (e.g., "Sakhir", "Jeddah")
            session_type: Session type ('FP1', 'FP2', 'FP3', 'Q', 'SQ', 'S', 'R')
            
        Returns:
            Session object or None if error
        """
        # Normalize race name first
        normalized_name = self._normalize_race_name(race_name)
        if normalized_name != race_name:
            print(f"Normalizing race name: '{race_name}' -> '{normalized_name}'")
        
        try:
            session = fastf1.get_session(season, normalized_name, session_type)
            session.load()
            
            # Check if results are available for qualifying/race sessions
            if session_type in ['Q', 'R', 'SQ', 'S']:
                if session.results is None or len(session.results) == 0:
                    print(f"Warning: {session_type} session loaded for {season} {race_name} but results are empty")
            
            return session
        except Exception as e:
            # Log all errors for debugging
            print(f"Error loading {session_type} session for {season} {race_name}: {e}")
            return None
    
    def _detect_sprint_weekend(self, season: int, race_name: str) -> bool:
        """
        Detect if a race weekend is a sprint weekend by checking for Sprint Qualifying session.
        
        Args:
            season: Season year
            race_name: Race name
            
        Returns:
            True if sprint weekend, False otherwise
        """
        # Try to load Sprint Qualifying session
        sprint_qualifying = self._get_session(season, race_name, 'SQ')
        return sprint_qualifying is not None
    
    def _get_driver_position(self, session, driver_code: str, session_type: str) -> Optional[int]:
        """
        Get driver position from session results.
        For practice sessions, calculate position from fastest lap times.
        For qualifying/race sessions, use SessionResults.
        Handles DNFs appropriately.
        
        Args:
            session: FastF1 session object
            driver_code: Driver code (e.g., "VER", "HAM")
            session_type: Session type to determine if we need to calculate positions
            
        Returns:
            Position (1-based) or None if driver not found/DNF
        """
        if session is None:
            return None
        
        try:
            # For practice sessions, calculate position from fastest lap times
            if session_type in ['FP1', 'FP2', 'FP3']:
                return self._get_practice_position(session, driver_code)
            
            # For qualifying and race sessions, use SessionResults
            results = session.results
            if results is None or len(results) == 0:
                print(f"Warning: No results available for {session_type} session for driver {driver_code}")
                return None
            
            # Find driver by Abbreviation
            driver_result = results[results['Abbreviation'] == driver_code]
            if len(driver_result) == 0:
                # Log available drivers for debugging
                available_drivers = results['Abbreviation'].tolist() if 'Abbreviation' in results.columns else []
                print(f"Warning: Driver {driver_code} not found in {session_type} results. Available drivers: {available_drivers}")
                return None
            
            # Check if driver DNF'd
            driver_row = driver_result.iloc[0]
            if hasattr(driver_row, 'dnf') and driver_row.dnf:
                # For DNFs, we might want to return None or a special value
                # You could also return the last known position before DNF
                # For now, return None to indicate no valid position
                return None
            
            # Get classified position
            classified_pos = driver_row['ClassifiedPosition']
            
            # Handle non-numeric positions (R, D, E, W, F, N)
            if isinstance(classified_pos, str):
                # These are not valid numeric positions
                return None
            
            position = driver_row['Position']
            # Handle NaN positions
            if pd.isna(position):
                return None
            
            return int(position)
        except Exception as e:
            print(f"Error getting position for {driver_code} in {session_type}: {e}")
            return None
    
    def _get_session_position(self, season: int, race_name: str, session_type: str, driver_code: str) -> Optional[int]:
        """
        Get driver position from a specific session.
        
        Args:
            season: Season year
            race_name: Race name
            session_type: Session type ('FP1', 'FP2', 'FP3', 'Q', 'SQ', 'S', 'R')
            driver_code: Driver code
            
        Returns:
            Position or None if session/driver not found
        """
        session = self._get_session(season, race_name, session_type)
        return self._get_driver_position(session, driver_code, session_type)
    
    def _calculate_weighted_score(self, positions: Dict[str, Optional[int]], is_sprint_weekend: bool) -> float:
        """
        Calculate weighted performance score from positions.
        
        Args:
            positions: Dictionary mapping session names to positions
            is_sprint_weekend: Whether this is a sprint weekend
            
        Returns:
            Weighted score (lower is better, like positions)
        """
        weights = WEIGHTS_SPRINT if is_sprint_weekend else WEIGHTS_STANDARD
        weighted_sum = 0.0
        has_valid_positions = False
        
        for session_name, weight in weights.items():
            # Map session names to position keys
            if session_name == 'FP1':
                pos_key = 'fp1_pos'
            elif session_name == 'FP2':
                pos_key = 'fp2_pos'
            elif session_name == 'FP3':
                pos_key = 'fp3_pos'
            elif session_name == 'Sprint Qualifying':
                pos_key = 'sprint_qualifying_pos'
            elif session_name == 'Sprint Race':
                pos_key = 'sprint_race_pos'
            elif session_name == 'Qualifying':
                pos_key = 'qualifying_pos'
            elif session_name == 'Race':
                pos_key = 'race_pos'
            else:
                continue
            
            position = positions.get(pos_key)
            if position is not None and not pd.isna(position):
                weighted_sum += position * weight
                has_valid_positions = True
        
        # Return weighted sum (lower is better, like positions)
        # Return NaN if no valid positions found
        if has_valid_positions:
            return weighted_sum
        else:
            return np.nan
    
    def _get_practice_position(self, session, driver_code: str) -> Optional[int]:
        """
        Calculate driver position in practice session based on fastest lap time.
        
        Args:
            session: FastF1 session object
            driver_code: Driver code
            
        Returns:
            Position (1-based) or None if driver not found
        """
        try:
            # Get all laps for this driver
            driver_laps = session.laps.pick_driver(driver_code)
            if len(driver_laps) == 0:
                return None
            
            # Get fastest lap time for this driver
            fastest_lap = driver_laps.pick_fastest()
            if fastest_lap is None or pd.isna(fastest_lap['LapTime']):
                return None
            
            driver_fastest_time = fastest_lap['LapTime']
            
            # Get fastest lap time for all drivers and rank them
            # Use session.drivers (driver numbers) and convert to codes
            all_fastest_times = []
            for driver_num in session.drivers:
                try:
                    # Get driver info to get abbreviation
                    driver_info = session.get_driver(driver_num)
                    driver_abbrev = driver_info['Abbreviation']
                    
                    driver_laps = session.laps.pick_driver(driver_num)
                    if len(driver_laps) > 0:
                        fastest = driver_laps.pick_fastest()
                        if fastest is not None and not pd.isna(fastest['LapTime']):
                            all_fastest_times.append({
                                'driver_code': driver_abbrev,
                                'time': fastest['LapTime']
                            })
                except:
                    continue
            
            if len(all_fastest_times) == 0:
                return None
            
            # Sort by fastest time (lower is better)
            all_fastest_times.sort(key=lambda x: x['time'])
            
            # Find position of this driver
            for idx, entry in enumerate(all_fastest_times, start=1):
                if entry['driver_code'] == driver_code:
                    return idx
            
            return None
        except Exception as e:
            print(f"Error calculating practice position for {driver_code}: {e}")
            return None
    
    def _get_driver_dnf_info(self, session, driver_code: str) -> Optional[Dict[str, str]]:
        """
        Get DNF information for a driver from session results.
        
        Args:
            session: FastF1 session object
            driver_code: Driver code
            
        Returns:
            Dictionary with 'status' and 'classified_position' or None if not DNF
        """
        if session is None:
            return None
        
        try:
            results = session.results
            if results is None or len(results) == 0:
                return None
            
            driver_result = results[results['Abbreviation'] == driver_code]
            if len(driver_result) == 0:
                return None
            
            driver_row = driver_result.iloc[0]
            
            # Check if driver DNF'd
            if hasattr(driver_row, 'dnf') and driver_row.dnf:
                return {
                    'status': str(driver_row.get('Status', 'Unknown')),
                    'classified_position': str(driver_row.get('ClassifiedPosition', 'Unknown')),
                    'dnf': True
                }
            
            return None
        except Exception as e:
            print(f"Error getting DNF info for {driver_code}: {e}")
            return None
    
    def _get_all_positions(self, season: int, race_name: str, driver_code: str, is_sprint_weekend: bool) -> Dict[str, Optional[int]]:
        """
        Get all session positions for a driver in a race.
        
        Args:
            season: Season year
            race_name: Race name
            driver_code: Driver code
            is_sprint_weekend: Whether this is a sprint weekend
            
        Returns:
            Dictionary of positions
        """
        positions = {
            'fp1_pos': None,
            'fp2_pos': None,
            'fp3_pos': None,
            'sprint_qualifying_pos': None,
            'sprint_race_pos': None,
            'qualifying_pos': None,
            'race_pos': None,
        }
        
        # Always get FP1, FP2, FP3, Qualifying, and Race positions
        positions['fp1_pos'] = self._get_session_position(season, race_name, 'FP1', driver_code)
        positions['fp2_pos'] = self._get_session_position(season, race_name, 'FP2', driver_code)
        positions['fp3_pos'] = self._get_session_position(season, race_name, 'FP3', driver_code)
        positions['qualifying_pos'] = self._get_session_position(season, race_name, 'Q', driver_code)
        positions['race_pos'] = self._get_session_position(season, race_name, 'R', driver_code)
        
        # Get sprint positions if sprint weekend
        if is_sprint_weekend:
            positions['sprint_qualifying_pos'] = self._get_session_position(season, race_name, 'SQ', driver_code)
            positions['sprint_race_pos'] = self._get_session_position(season, race_name, 'S', driver_code)
        
        return positions
    
    def generate_performance_data(self, input_csv_path: str = "car_race_summary.csv") -> pd.DataFrame:
        """
        Generate qualifying to race performance data for all races.
        
        Args:
            input_csv_path: Path to car_race_summary.csv
            
        Returns:
            DataFrame with performance data
        """
        print(f"Loading race summary from {input_csv_path}...")
        race_summary = self.load_race_summary(input_csv_path)
        print(f"Loaded {len(race_summary)} driver-race records")
        
        # Get unique races
        unique_races = race_summary[['season', 'race_name', 'round', 'circuit_type']].drop_duplicates()
        print(f"Processing {len(unique_races)} unique races...")
        
        performance_records = []
        
        for idx, race_info in unique_races.iterrows():
            season = int(race_info['season'])
            race_name = race_info['race_name']
            round_num = race_info['round']
            circuit_type = race_info['circuit_type']
            
            print(f"Processing {season} {race_name} (Round {round_num})...")
            
            # Detect sprint weekend once per race
            is_sprint_weekend = self._detect_sprint_weekend(season, race_name)
            weekend_type = "Sprint" if is_sprint_weekend else "Standard"
            print(f"  Weekend type: {weekend_type}")
            
            # Get all drivers for this race
            race_drivers = race_summary[
                (race_summary['season'] == season) & 
                (race_summary['race_name'] == race_name)
            ]
            
            for driver_idx, driver_row in race_drivers.iterrows():
                driver_code = driver_row['driver']
                team = driver_row['team']
                
                # Get all positions for this driver
                positions = self._get_all_positions(season, race_name, driver_code, is_sprint_weekend)
                
                # Get DNF information for race
                race_session = self._get_session(season, race_name, 'R')
                dnf_info = self._get_driver_dnf_info(race_session, driver_code)
                
                # Calculate weighted score
                weighted_score = self._calculate_weighted_score(positions, is_sprint_weekend)
                
                # Create record
                record = {
                    'season': season,
                    'driver': driver_code,
                    'race_name': race_name,
                    'round': round_num,
                    'circuit_type': circuit_type,
                    'team': team,
                    **positions,
                    'race_dnf_status': dnf_info['status'] if dnf_info else None,
                    'race_classified_position': dnf_info['classified_position'] if dnf_info else None,
                    'weighted_performance_score': weighted_score,
                }
                
                performance_records.append(record)
            
            # Small delay to avoid overwhelming the API
            time.sleep(0.5)
        
        # Create DataFrame
        performance_df = pd.DataFrame(performance_records)
        
        # Ensure all columns are present
        for col in columns:
            if col not in performance_df.columns:
                performance_df[col] = np.nan
        
        # Reorder columns
        performance_df = performance_df[columns]
        
        # Sort by season, round, driver
        performance_df = performance_df.sort_values(['season', 'round', 'driver']).reset_index(drop=True)
        
        print(f"Generated performance data for {len(performance_df)} driver-race records")
        return performance_df
    
    def save_performance_data(self, performance_df: pd.DataFrame, output_path: str = "qualifying_to_race_performance.csv"):
        """Save performance DataFrame to CSV."""
        performance_df.to_csv(output_path, index=False)
        print(f"Saved performance data to {output_path}")


def main(input_csv_path: str = "car_race_summary.csv",
         output_csv_path: str = "qualifying_to_race_performance.csv",
         cache_dir: str = "fastf1_cache"):
    """
    Main function to generate qualifying to race performance data.
    
    Args:
        input_csv_path: Path to input car_race_summary.csv
        output_csv_path: Path to output qualifying_to_race_performance.csv
        cache_dir: Directory for FastF1 cache
    """
    loader = QualifyingToRacePerformance(cache_dir=cache_dir)
    performance_df = loader.generate_performance_data(input_csv_path)
    loader.save_performance_data(performance_df, output_csv_path)
    return performance_df


if __name__ == "__main__":
    import sys
    
    # Allow command line arguments
    input_path = sys.argv[1] if len(sys.argv) > 1 else "car_race_summary.csv"
    output_path = sys.argv[2] if len(sys.argv) > 2 else "qualifying_to_race_performance.csv"
    
    main(input_csv_path=input_path, output_csv_path=output_path)


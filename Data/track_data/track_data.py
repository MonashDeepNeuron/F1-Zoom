from __future__ import annotations

import fastf1
import pandas as pd
import warnings
import os
from pathlib import Path
import math

# Suppress FastF1 warnings for cleaner output
warnings.filterwarnings('ignore')
cache_dir = Path.home() / '.fastf1_cache'
cache_dir.mkdir(parents=True, exist_ok=True)
fastf1.Cache.enable_cache(str(cache_dir))


def get_race_incidents(year: int, race_name: str) -> dict:
    print(f"Loading {year} {race_name}...", end=' ')
    
    try:
        # Load race session
        session = fastf1.get_session(year, race_name, 'R')
        session.load(laps=True, telemetry=False, weather=False, messages=False)
        
        # Initialize incident flags
        has_sc = has_vsc = has_red = False
        
        # Check track status for incidents
        if hasattr(session, 'track_status') and session.track_status is not None:
            if not session.track_status.empty and 'Status' in session.track_status.columns:
                status = session.track_status['Status'].astype(str)
                has_sc = '4' in status.values  # Status code 4 = Safety Car
                has_vsc = ('6' in status.values or '7' in status.values)  # 6/7 = VSC
                has_red = '5' in status.values  # Status code 5 = Red Flag
        
        print(f"✓ (SC:{has_sc}, VSC:{has_vsc}, Red:{has_red})")
        
        return {
            'season': year,
            'race_name': race_name,
            'has_safety_car': has_sc,
            'has_vsc': has_vsc,
            'has_red_flag': has_red
        }
        
    except Exception as e:
        print(f"Error: {e}")
        return None

def overtakability_ranking(year: int, race_name: str) -> dict:    
    print(f"Analyzing overtakes for {year} {race_name}...")
    
    try:
        # Load race session with all necessary data
        session = fastf1.get_session(year, race_name, 'R')
        session.load(laps=True, telemetry=False, weather=False, messages=False)
        
        laps = session.laps
        
        # Validate data
        if laps is None or laps.empty:
            print("No lap data available")
            return None
        
        required_cols = ['LapNumber', 'Position', 'Driver', 'PitOutTime']
        if not all(col in laps.columns for col in required_cols):
            print("Missing required columns")
            return None
        
        max_lap = int(laps['LapNumber'].dropna().max())
        if max_lap < 1:
            print("Not enough laps")
            return None
        
        # Get track status data to identify safety car/VSC/red flag laps
        excluded_laps = set()
        if hasattr(session, 'track_status') and session.track_status is not None:
            if not session.track_status.empty and 'Status' in session.track_status.columns:
                status_data = session.track_status.copy()
                
                # Convert Time to seconds if it's a timedelta
                if 'Time' in status_data.columns:
                    status_data['TimeSeconds'] = status_data['Time'].dt.total_seconds()
                    
                    # Map status times to lap numbers
                    for _, status_row in status_data.iterrows():
                        status_code = str(status_row['Status'])
                        # 4=SC, 5=Red, 6=VSC, 7=VSC Ending
                        if status_code in ['4', '5', '6', '7']:
                            status_time = status_row['TimeSeconds']
                            
                            # Find which lap(s) this corresponds to
                            for lap_num in range(1, max_lap + 1):
                                lap_data = laps[laps['LapNumber'] == lap_num]
                                if not lap_data.empty and 'LapStartTime' in lap_data.columns:
                                    # Check if status occurred during this lap
                                    lap_times = lap_data['LapStartTime'].dt.total_seconds()
                                    if not lap_times.empty:
                                        if lap_times.min() <= status_time <= lap_times.max() + 120:
                                            excluded_laps.add(lap_num)
        
        print(f"  Excluding {len(excluded_laps)} laps due to SC/VSC/Red flags: {sorted(excluded_laps)}")
        
        # Count overtakes
        total_overtakes = 0
        overtakes_by_lap = {}
        
        for lap_num in range(1, max_lap + 1):
            # Skip if this lap had safety car or other incidents
            if lap_num in excluded_laps:
                continue
            
            # Get previous lap positions (or grid for lap 1)
            if lap_num == 1:
                # For lap 1, use grid positions
                prev_positions = {}
                for driver in laps['Driver'].unique():
                    driver_laps = laps[laps['Driver'] == driver].sort_values('LapNumber')
                    if not driver_laps.empty:
                        # Get their position from session.results which has grid positions
                        if hasattr(session, 'results') and session.results is not None:
                            driver_result = session.results[session.results['Abbreviation'] == driver]
                            if not driver_result.empty and 'GridPosition' in driver_result.columns:
                                grid_pos = driver_result['GridPosition'].values[0]
                                if pd.notna(grid_pos):
                                    prev_positions[driver] = int(grid_pos)
            else:
                prev_lap = laps[laps['LapNumber'] == lap_num - 1]
                prev_positions = {}
                for _, row in prev_lap.iterrows():
                    if pd.notna(row['Position']):
                        prev_positions[row['Driver']] = int(row['Position'])
            
            curr_lap = laps[laps['LapNumber'] == lap_num]
            
            # Track position changes (gains only, to avoid double counting)
            position_changes = []
            
            for _, curr_row in curr_lap.iterrows():
                driver = curr_row['Driver']
                
                # Skip if driver wasn't in previous lap
                if driver not in prev_positions:
                    continue
                
                curr_pos = curr_row['Position']
                if pd.isna(curr_pos):
                    continue
                
                curr_pos = int(curr_pos)
                prev_pos = prev_positions[driver]
                
                # Only count position gains (lower number = better)
                if curr_pos < prev_pos:
                    # Check if this driver pitted on this lap
                    driver_pitted = pd.notna(curr_row['PitOutTime'])
                    
                    if not driver_pitted:
                        # Check if any driver they passed pitted
                        # They passed drivers who were between curr_pos and prev_pos
                        passed_legitimate = False
                        
                        for other_driver in prev_positions:
                            if other_driver == driver:
                                continue
                            
                            other_prev_pos = prev_positions[other_driver]
                            
                            # This is a driver they could have passed
                            if curr_pos <= other_prev_pos < prev_pos:
                                # Check if other driver pitted
                                other_curr = curr_lap[curr_lap['Driver'] == other_driver]
                                if not other_curr.empty:
                                    other_pitted = pd.notna(other_curr['PitOutTime'].values[0])
                                    if not other_pitted:
                                        # This is a legitimate overtake
                                        passed_legitimate = True
                                        break
                        
                        if passed_legitimate:
                            positions_gained = prev_pos - curr_pos
                            position_changes.append({
                                'driver': driver,
                                'from': prev_pos,
                                'to': curr_pos,
                                'gained': positions_gained
                            })
            
            # Count total positions gained (this is our overtake metric)
            lap_overtakes = sum(pc['gained'] for pc in position_changes)
            
            if lap_overtakes > 0:
                total_overtakes += lap_overtakes
                overtakes_by_lap[lap_num] = lap_overtakes
        
        # Calculate metrics
        racing_laps = max_lap - len(excluded_laps)
        avg_field_size = laps.groupby('LapNumber')['Driver'].nunique().mean()
        
        overtakes_per_lap = total_overtakes / racing_laps if racing_laps > 0 else 0
        
        # Normalize by field size (overtakes per driver per lap)
        overtake_density = total_overtakes / (racing_laps * avg_field_size) if (racing_laps * avg_field_size) > 0 else 0
        
        print(f"✓ Found {total_overtakes} overtakes across {racing_laps} racing laps")
        
        return {
            'season': year,
            'race_name': race_name,
            'total_overtakes': total_overtakes,
            'total_laps': max_lap,
            'racing_laps': racing_laps,
            'excluded_laps': len(excluded_laps),
            'avg_field_size': round(avg_field_size, 1),
            'overtakes_per_lap': round(overtakes_per_lap, 2),
            'overtake_density': round(overtake_density, 4),
            'top_overtaking_laps': dict(sorted(overtakes_by_lap.items(), 
                                               key=lambda x: x[1], 
                                               reverse=True)[:5])
        }
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        return None



def main(start_year: int, start_race_name: str, finish_year: int, finish_race_name: str, 
         output_csv: str = "track_overtaking_data.csv") -> pd.DataFrame:
    """
    Main function to analyze overtaking and incidents for all races in a range.
    Aggregates by track and returns a DataFrame with the results.
    
    Args:
        start_year: Starting year
        start_race_name: Name of first race to include
        finish_year: Ending year
        finish_race_name: Name of last race to include
        output_csv: Path to save the output CSV file
        
    Returns:
        DataFrame with columns: track_name, score, avg_overtakes, sc_pct, vsc_pct, red_pct
    """
    all_results = []
    found_start = False
    found_finish = False
    
    # Iterate through each year in the range
    for year in range(start_year, finish_year + 1):
        try:
            schedule = fastf1.get_event_schedule(year)
            races = schedule[schedule['EventFormat'].notna()]
        except Exception as e:
            print(f"Could not load schedule for {year}: {e}")
            continue
        
        for _, race in races.iterrows():
            race_name = race['EventName']
            
            # Skip non-race events
            if 'Testing' in race_name or 'Pre-Season' in race_name:
                continue
            
            # Check if we've reached the start race
            if year == start_year and race_name == start_race_name:
                found_start = True
            
            # Only process if we're within the range
            if found_start and not found_finish:
                # Get overtaking data
                overtake_result = overtakability_ranking(year, race_name)
                
                # Get incident data
                incident_result = get_race_incidents(year, race_name)
                
                # Merge results if overtake data succeeded
                if overtake_result:
                    if incident_result:
                        overtake_result['has_safety_car'] = incident_result['has_safety_car']
                        overtake_result['has_vsc'] = incident_result['has_vsc']
                        overtake_result['has_red_flag'] = incident_result['has_red_flag']
                    else:
                        overtake_result['has_safety_car'] = None
                        overtake_result['has_vsc'] = None
                        overtake_result['has_red_flag'] = None
                    
                    all_results.append(overtake_result)
            
            # Check if we've reached the finish race
            if year == finish_year and race_name == finish_race_name:
                found_finish = True
                break
        
        if found_finish:
            break
    
    if not all_results:
        print("No results collected!")
        return pd.DataFrame()
    
    # Aggregate results by track name
    from collections import defaultdict
    track_data = defaultdict(lambda: {
        'overtakes': [],
        'sc_count': 0,
        'vsc_count': 0,
        'red_count': 0,
        'race_count': 0
    })
    
    for result in all_results:
        track_name = result['race_name']
        track_data[track_name]['overtakes'].append(result['total_overtakes'])
        track_data[track_name]['race_count'] += 1
        if result.get('has_safety_car'):
            track_data[track_name]['sc_count'] += 1
        if result.get('has_vsc'):
            track_data[track_name]['vsc_count'] += 1
        if result.get('has_red_flag'):
            track_data[track_name]['red_count'] += 1
    
    # Calculate aggregated metrics per track
    aggregated_results = []
    for track_name, data in track_data.items():
        avg_overtakes = sum(data['overtakes']) / len(data['overtakes'])
        sc_pct = (data['sc_count'] / data['race_count']) * 100
        vsc_pct = (data['vsc_count'] / data['race_count']) * 100
        red_pct = (data['red_count'] / data['race_count']) * 100
        
        aggregated_results.append({
            'track_name': track_name,
            'avg_overtakes': round(avg_overtakes, 1),
            'sc_pct': round(sc_pct, 1),
            'vsc_pct': round(vsc_pct, 1),
            'red_pct': round(red_pct, 1)
        })
    
    # Calculate min and max overtakes for normalization
    overtake_counts = [r['avg_overtakes'] for r in aggregated_results]
    min_overtakes = min(overtake_counts)
    max_overtakes = max(overtake_counts)
    
    print(f"\n📊 Overtake Range: Min = {min_overtakes}, Max = {max_overtakes}")
    
    # Normalize scores to 0-100 based on min/max
    for result in aggregated_results:
        if max_overtakes > min_overtakes:
            normalized_score = ((result['avg_overtakes'] - min_overtakes) / 
                               (max_overtakes - min_overtakes)) * 100
        else:
            normalized_score = 50
        result['score'] = round(normalized_score, 1)
    
    # Create DataFrame with desired column order
    df = pd.DataFrame(aggregated_results)
    df = df[['track_name', 'score', 'avg_overtakes', 'sc_pct', 'vsc_pct', 'red_pct']]
    df = df.sort_values('score', ascending=False).reset_index(drop=True)
    
    # Save to CSV
    df.to_csv(output_csv, index=False)
    print(f"\n✅ Data saved to {output_csv}")
    
    # Print the DataFrame
    print("\n" + "=" * 80)
    print("🏎️  TRACK OVERTAKING RANKING")
    print("=" * 80)
    print(df.to_string(index=False))
    print("=" * 80)
    
    return df


if __name__ == "__main__":
    df = main(
        start_year=2022,
        start_race_name="Bahrain Grand Prix",
        finish_year=2024,
        finish_race_name="Abu Dhabi Grand Prix",
        output_csv="track_overtaking_data.csv"
    )
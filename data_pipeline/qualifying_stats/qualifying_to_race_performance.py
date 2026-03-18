# Extract driver positions from FP1, FP2, FP3, Qualifying, Sprint Qualifying, Sprint Race, and Race sessions
# Apply weights and calculate weighted performance scores for Monte Carlo simulation

from __future__ import annotations

import fastf1
import os
import sys
import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'config'))
from driver_config import (
    get_team_from_driver as _cfg_get_team,
    get_driver_from_number,
    is_sprint_weekend,
)

# Define column order for output CSV
columns = [
    # Metadata
    "season", "driver", "race_name", "round", "circuit_type", "team", # basic data which we need to match the other csv files
    
    # Positions
    "fp1_pos", "fp2_pos", "fp3_pos", 
    "sprint_qualifying_pos", "sprint_race_pos", # fp2, fp3, sprint quali and sprint race positions are dependent on whether or not the race has a sprint race of if it is a standard weekend
    "qualifying_pos", "race_pos",
    
    # DNF Information
    "race_dnf_status",  # Possible values include but are not limited to ‘Finished’, ‘+ 1 Lap’, ‘Crash’, ‘Gearbox’, … (values only given if session is ‘Race’, ‘Sprint’, ‘Sprint Shootout’ or ‘Sprint Qualifying’) - FAST F1 Documentation
    "race_classified_position",
    
    # Weighted score
    "weighted_performance_score", # we compute this metric as we need to score the overall perormance of the driver + car over the weekend whilst taking into consideration that free practice is less important the qualifying or race results
]

def get_round_from_race_name(race_name: str, season: int) -> int:
    """Get round number from FastF1 schedule."""
    try:
        schedule = fastf1.get_event_schedule(season)
        race = schedule[schedule['EventName'] == race_name]
        if not race.empty:
            return int(race.iloc[0]['RoundNumber'])
    except:
        pass
    return 1

def get_team_from_driver(driver_code: str, season: int, race_name: str) -> str:
    """Resolve team via shared config, converting race_name to a round number."""
    race_number = get_round_from_race_name(race_name, season)
    return _cfg_get_team(driver_code, season=season, race_number=race_number)

def format_lap_time(lap_time) -> str:
    """Format Timedelta lap time as M:SS.mmm (e.g., 1:33.648). Returns np.nan if input is NaN/None."""
    if lap_time is None or pd.isna(lap_time):
        return np.nan
    total_seconds = lap_time.total_seconds()
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    milliseconds = int((total_seconds % 1) * 1000)
    return f"{minutes}:{seconds:02d}.{milliseconds:03d}"


def lap_time_to_seconds(lap_time) -> float:
    """Convert Timedelta lap time to total seconds as float. Returns np.nan if input is NaN/None."""
    if lap_time is None or pd.isna(lap_time):
        return np.nan
    return lap_time.total_seconds()


def sprint_or_standard_weekend(race_name: str, season: int = 2025) -> bool:
    """Return True if *race_name* is a sprint weekend (delegates to shared config)."""
    return is_sprint_weekend(race_name, season=season)


def free_practice_performance(year: int, race_name: str) -> pd.DataFrame:
    
    rows = []
    
    if not sprint_or_standard_weekend(race_name, year):
        # get all free practice data
        
        print("This is a STANDARD WEEKEND")
        
        fp1 = fastf1.get_session(year, race_name, 'FP1')
        fp1.load()
        fp1_laps = fp1.laps.pick_quicklaps() # automatically filters for flying laps
        
        fp2 = fastf1.get_session(year, race_name, 'FP2')
        fp2.load()
        fp2_laps = fp2.laps.pick_quicklaps()
        
        fp3 = fastf1.get_session(year, race_name, 'FP3')
        fp3.load()
        fp3_laps = fp3.laps.pick_quicklaps()
        
        
        for session, laps in [(fp1, fp1_laps), (fp2, fp2_laps), (fp3, fp3_laps)]:
            
            for driver in session.drivers:
                
                driv_laps = laps.pick_driver(driver)
                if len(driv_laps) > 0:
                    fastest_lap = driv_laps['LapTime'].min()
                    print(driver, format_lap_time(fastest_lap)) # comment out print statements so console stays clean
        
        fp1_fastest = (
            fp1_laps.groupby("Driver")["LapTime"]
            .min()
            .sort_values()
        )
        fp1_pos = {drv: pos for pos, (drv, _) in enumerate(fp1_fastest.items(), start=1)}
        fp1_fastest_dict = fp1_fastest.to_dict()

        fp2_fastest = (
            fp2_laps.groupby("Driver")["LapTime"]
            .min()
            .sort_values()
        )
        fp2_pos = {drv: pos for pos, (drv, _) in enumerate(fp2_fastest.items(), start=1)}
        fp2_fastest_dict = fp2_fastest.to_dict()

        fp3_fastest = (
            fp3_laps.groupby("Driver")["LapTime"]
            .min()
            .sort_values()
        )
        fp3_pos = {drv: pos for pos, (drv, _) in enumerate(fp3_fastest.items(), start=1)}
        fp3_fastest_dict = fp3_fastest.to_dict()
        
        for driver_code in fp3_laps['Driver'].unique():
            team = get_team_from_driver(driver_code, year, race_name)
            
            row = {
                "season": year,
                "race_name": race_name,
                "driver": driver_code,
                "team": team,
                "fp1_pos": fp1_pos.get(driver_code, np.nan),
                "fp1_time_fastest_lap": format_lap_time(fp1_fastest_dict.get(driver_code)),
                "fp2_pos": fp2_pos.get(driver_code, np.nan),
                "fp2_time_fastest_lap": format_lap_time(fp2_fastest_dict.get(driver_code)),
                "fp3_pos": fp3_pos.get(driver_code, np.nan),
                "fp3_time_fastest_lap": format_lap_time(fp3_fastest_dict.get(driver_code)),
            }
            rows.append(row)
                    

    else:
        
        print("This is a SPRINT WEEKEND")
        
        fp1 = fastf1.get_session(year, race_name, 'FP1')
        fp1.load()
        fp1_laps = fp1.laps.pick_quicklaps() # automatically filters for flying laps
        
        
        for driver in fp1.drivers:
            driv_laps = fp1_laps.pick_driver(driver)
            if len(driv_laps) > 0:
                fastest_lap = driv_laps['LapTime'].min()
                print(driver, format_lap_time(fastest_lap))
        
        fp1_fastest = (
            fp1_laps.groupby("Driver")["LapTime"]
            .min()
            .sort_values()
        )
        fp1_pos = {drv: pos for pos, (drv, _) in enumerate(fp1_fastest.items(), start=1)}
        fp1_fastest_dict = fp1_fastest.to_dict()

        for driver_code in fp1_laps['Driver'].unique():
            team = get_team_from_driver(driver_code, year, race_name)
            
            row = {
                "season": year,
                "race_name": race_name,
                "driver": driver_code,
                "team": team,
                "fp1_pos": fp1_pos.get(driver_code, np.nan),
                "fp1_time_fastest_lap": format_lap_time(fp1_fastest_dict.get(driver_code)),
            }
            rows.append(row)
            
    
    return pd.DataFrame(rows)

def qualifying_performance(year: int, race_name: str) -> pd.DataFrame:
    
    rows = []
    
    if not sprint_or_standard_weekend(race_name, year):
        
        # only a standard qualifying
        qualifying_session = fastf1.get_session(year, race_name, "Qualifying")
        qualifying_session.load()
        qualifying_results = qualifying_session.results
        qualifying_results = qualifying_results.sort_values('Position').reset_index(drop=True)
        
        # Calculate Q1, Q2, Q3 position rankings based on times
        # Q1 ranking - all drivers participate
        q1_times = qualifying_results[['Abbreviation', 'Q1']].dropna(subset=['Q1']).copy()
        q1_times['Q1_seconds'] = q1_times['Q1'].apply(lap_time_to_seconds)
        q1_times = q1_times.sort_values('Q1_seconds')
        q1_pos_dict = {row['Abbreviation']: pos for pos, (_, row) in enumerate(q1_times.iterrows(), start=1)}
        q1_seconds_dict = dict(zip(q1_times['Abbreviation'], q1_times['Q1_seconds']))
        
        # Q2 ranking - top 15 from Q1
        q2_times = qualifying_results[['Abbreviation', 'Q2']].dropna(subset=['Q2']).copy()
        q2_times['Q2_seconds'] = q2_times['Q2'].apply(lap_time_to_seconds)
        q2_times = q2_times.sort_values('Q2_seconds')
        q2_pos_dict = {row['Abbreviation']: pos for pos, (_, row) in enumerate(q2_times.iterrows(), start=1)}
        q2_seconds_dict = dict(zip(q2_times['Abbreviation'], q2_times['Q2_seconds']))
        
        # Q3 ranking - top 10 from Q2
        q3_times = qualifying_results[['Abbreviation', 'Q3']].dropna(subset=['Q3']).copy()
        q3_times['Q3_seconds'] = q3_times['Q3'].apply(lap_time_to_seconds)
        q3_times = q3_times.sort_values('Q3_seconds')
        q3_pos_dict = {row['Abbreviation']: pos for pos, (_, row) in enumerate(q3_times.iterrows(), start=1)}
        q3_seconds_dict = dict(zip(q3_times['Abbreviation'], q3_times['Q3_seconds']))
        
        for idx, row in qualifying_results.iterrows():
            driver_code = row['Abbreviation']
            
            rows.append({
                "season": year,
                "race_name": race_name,
                "driver": driver_code,
                "team": row['TeamName'],
                "Qualifying_Final_Grid_Position": int(row['Position']) if pd.notna(row['Position']) else np.nan,
                # Q1 data
                "Q1_time_seconds": q1_seconds_dict.get(driver_code, np.nan),
                "Q1_position": q1_pos_dict.get(driver_code, np.nan),
                "Q1_fastest_lap": format_lap_time(row.get('Q1', pd.NaT)),
                # Q2 data
                "Q2_time_seconds": q2_seconds_dict.get(driver_code, np.nan),
                "Q2_position": q2_pos_dict.get(driver_code, np.nan),
                "Q2_fastest_lap": format_lap_time(row.get('Q2', pd.NaT)),
                # Q3 data
                "Q3_time_seconds": q3_seconds_dict.get(driver_code, np.nan),
                "Q3_position": q3_pos_dict.get(driver_code, np.nan),
                "Q3_fastest_lap": format_lap_time(row.get('Q3', pd.NaT))
            })

    else:
        
        print("This is a SPRINT WEEKEND")
        
        sprint_qualifying_session = fastf1.get_session(year, race_name, "Sprint Qualifying")
        sprint_qualifying_session.load()
        sprint_qualifying_results = sprint_qualifying_session.results
        
        qualifying_session = fastf1.get_session(year, race_name, "Qualifying")
        qualifying_session.load()
        qualifying_results = qualifying_session.results
        
        # Sprint Qualifying rankings
        sq1_times = sprint_qualifying_results[['Abbreviation', 'Q1']].dropna(subset=['Q1']).copy()
        sq1_times['SQ1_seconds'] = sq1_times['Q1'].apply(lap_time_to_seconds)
        sq1_times = sq1_times.sort_values('SQ1_seconds')
        sq1_pos_dict = {row['Abbreviation']: pos for pos, (_, row) in enumerate(sq1_times.iterrows(), start=1)}
        sq1_seconds_dict = dict(zip(sq1_times['Abbreviation'], sq1_times['SQ1_seconds']))
        
        sq2_times = sprint_qualifying_results[['Abbreviation', 'Q2']].dropna(subset=['Q2']).copy()
        sq2_times['SQ2_seconds'] = sq2_times['Q2'].apply(lap_time_to_seconds)
        sq2_times = sq2_times.sort_values('SQ2_seconds')
        sq2_pos_dict = {row['Abbreviation']: pos for pos, (_, row) in enumerate(sq2_times.iterrows(), start=1)}
        sq2_seconds_dict = dict(zip(sq2_times['Abbreviation'], sq2_times['SQ2_seconds']))
        
        sq3_times = sprint_qualifying_results[['Abbreviation', 'Q3']].dropna(subset=['Q3']).copy()
        sq3_times['SQ3_seconds'] = sq3_times['Q3'].apply(lap_time_to_seconds)
        sq3_times = sq3_times.sort_values('SQ3_seconds')
        sq3_pos_dict = {row['Abbreviation']: pos for pos, (_, row) in enumerate(sq3_times.iterrows(), start=1)}
        sq3_seconds_dict = dict(zip(sq3_times['Abbreviation'], sq3_times['SQ3_seconds']))
        
        # Main Qualifying rankings
        q1_times = qualifying_results[['Abbreviation', 'Q1']].dropna(subset=['Q1']).copy()
        q1_times['Q1_seconds'] = q1_times['Q1'].apply(lap_time_to_seconds)
        q1_times = q1_times.sort_values('Q1_seconds')
        q1_pos_dict = {row['Abbreviation']: pos for pos, (_, row) in enumerate(q1_times.iterrows(), start=1)}
        q1_seconds_dict = dict(zip(q1_times['Abbreviation'], q1_times['Q1_seconds']))
        
        q2_times = qualifying_results[['Abbreviation', 'Q2']].dropna(subset=['Q2']).copy()
        q2_times['Q2_seconds'] = q2_times['Q2'].apply(lap_time_to_seconds)
        q2_times = q2_times.sort_values('Q2_seconds')
        q2_pos_dict = {row['Abbreviation']: pos for pos, (_, row) in enumerate(q2_times.iterrows(), start=1)}
        q2_seconds_dict = dict(zip(q2_times['Abbreviation'], q2_times['Q2_seconds']))
        
        q3_times = qualifying_results[['Abbreviation', 'Q3']].dropna(subset=['Q3']).copy()
        q3_times['Q3_seconds'] = q3_times['Q3'].apply(lap_time_to_seconds)
        q3_times = q3_times.sort_values('Q3_seconds')
        q3_pos_dict = {row['Abbreviation']: pos for pos, (_, row) in enumerate(q3_times.iterrows(), start=1)}
        q3_seconds_dict = dict(zip(q3_times['Abbreviation'], q3_times['Q3_seconds']))
        
        sprint_qualifying_dict = {}
        for idx, row in sprint_qualifying_results.iterrows():
            driver_code = row['Abbreviation']
            sprint_qualifying_dict[driver_code] = {
                "team": row['TeamName'],
                "Sprint_Qualifying_Final_Grid_Position": int(row['Position']) if pd.notna(row['Position']) else np.nan,
                "SQ1_time_seconds": sq1_seconds_dict.get(driver_code, np.nan),
                "SQ1_position": sq1_pos_dict.get(driver_code, np.nan),
                "SQ1_fastest_lap": format_lap_time(row.get('Q1', pd.NaT)),
                "SQ2_time_seconds": sq2_seconds_dict.get(driver_code, np.nan),
                "SQ2_position": sq2_pos_dict.get(driver_code, np.nan),
                "SQ2_fastest_lap": format_lap_time(row.get('Q2', pd.NaT)),
                "SQ3_time_seconds": sq3_seconds_dict.get(driver_code, np.nan),
                "SQ3_position": sq3_pos_dict.get(driver_code, np.nan),
                "SQ3_fastest_lap": format_lap_time(row.get('Q3', pd.NaT))
            }
        
        for idx, row in qualifying_results.iterrows():
            driver_code = row['Abbreviation']
            sprint_data = sprint_qualifying_dict.get(driver_code, {})
            
            rows.append({
                "season": year,
                "race_name": race_name,
                "driver": driver_code,
                "team": sprint_data.get("team", row['TeamName']),
                # Sprint Qualifying data
                "Sprint_Qualifying_Final_Grid_Position": sprint_data.get("Sprint_Qualifying_Final_Grid_Position", np.nan),
                "SQ1_time_seconds": sprint_data.get("SQ1_time_seconds", np.nan),
                "SQ1_position": sprint_data.get("SQ1_position", np.nan),
                "SQ1_fastest_lap": sprint_data.get("SQ1_fastest_lap", np.nan),
                "SQ2_time_seconds": sprint_data.get("SQ2_time_seconds", np.nan),
                "SQ2_position": sprint_data.get("SQ2_position", np.nan),
                "SQ2_fastest_lap": sprint_data.get("SQ2_fastest_lap", np.nan),
                "SQ3_time_seconds": sprint_data.get("SQ3_time_seconds", np.nan),
                "SQ3_position": sprint_data.get("SQ3_position", np.nan),
                "SQ3_fastest_lap": sprint_data.get("SQ3_fastest_lap", np.nan),
                # Main Qualifying data
                "Qualifying_Final_Grid_Position": int(row['Position']) if pd.notna(row['Position']) else np.nan,
                "Q1_time_seconds": q1_seconds_dict.get(driver_code, np.nan),
                "Q1_position": q1_pos_dict.get(driver_code, np.nan),
                "Q1_fastest_lap": format_lap_time(row.get('Q1', pd.NaT)),
                "Q2_time_seconds": q2_seconds_dict.get(driver_code, np.nan),
                "Q2_position": q2_pos_dict.get(driver_code, np.nan),
                "Q2_fastest_lap": format_lap_time(row.get('Q2', pd.NaT)),
                "Q3_time_seconds": q3_seconds_dict.get(driver_code, np.nan),
                "Q3_position": q3_pos_dict.get(driver_code, np.nan),
                "Q3_fastest_lap": format_lap_time(row.get('Q3', pd.NaT))
            })
        
    return pd.DataFrame(rows)
    

def race_performance(year: int, race_name: str) -> pd.DataFrame:
    
    rows = []
    
    if not sprint_or_standard_weekend(race_name, year):
        
        # only a standard race
        race_session = fastf1.get_session(year, race_name, "Race")
        race_session.load()
        race_results = race_session.results
        
        for idx, row in race_results.iterrows():
            driver_code = row['Abbreviation']
            driv_laps = race_session.laps.pick_driver(driver_code)
            fastest_lap = driv_laps['LapTime'].min()
            
            rows.append({
                "season": year,
                "race_name": race_name,
                "driver": driver_code,
                "team": row['TeamName'],
                "Race_Finishing_Position": int(row['Position']) if pd.notna(row['Position']) else np.nan,
                "fastest_lap": format_lap_time(fastest_lap), 
            })

    else:
        
        print("This is a SPRINT WEEKEND")
        
        sprint_race_session = fastf1.get_session(year, race_name, "Sprint")
        sprint_race_session.load()
        sprint_race_results = sprint_race_session.results
        
        race_session = fastf1.get_session(year, race_name, "Race")
        race_session.load()
        race_results = race_session.results
        
        sprint_race_dict = {}
        for idx, row in sprint_race_results.iterrows():
            driver_code = row['Abbreviation']
            driv_laps = sprint_race_session.laps.pick_driver(driver_code)
            fastest_lap = driv_laps['LapTime'].min()
            sprint_race_dict[driver_code] = {
                "team": row['TeamName'],
                "sprint_race_final_position": int(row['Position']) if pd.notna(row['Position']) else np.nan,
                "sprint_race_fastest_lap": format_lap_time(fastest_lap),   
            }
        
        
        for idx, row in race_results.iterrows():
            driver_code = row['Abbreviation']
            driv_laps = race_session.laps.pick_driver(driver_code)
            fastest_lap = driv_laps['LapTime'].min()
            sprint_data = sprint_race_dict.get(driver_code, {})
            
            rows.append({
                "season": year,
                "race_name": race_name,
                "driver": driver_code,
                "team": sprint_data.get("team", row['TeamName']),
                "sprint_race_final_position": sprint_data.get("sprint_race_final_position", np.nan),
                "sprint_race_fastest_lap": sprint_data.get("sprint_race_fastest_lap", np.nan),
                "race_final_position": int(row['Position']) if pd.notna(row['Position']) else np.nan,
                "race_fastest_lap": format_lap_time(fastest_lap), 
            })
        
    return pd.DataFrame(rows)

def calculate_rolling_avg_positions(df: pd.DataFrame, windows: list = [3, 5, 7]) -> pd.DataFrame:
    # Make a copy
    df = df.copy()
    
    # Ensure race_pos is numeric
    df['race_pos'] = pd.to_numeric(df['race_pos'], errors='coerce')
    
    # Create a race order column if it doesn't exist
    # This creates a sequential race number within each season
    if 'round' not in df.columns:
        print("Creating sequential round numbers within each season...")
        df['round'] = df.groupby('season').cumcount() + 1
    
    # Sort by driver, season, and round to ensure chronological order
    print("Sorting data chronologically by driver, season, and round...")
    df = df.sort_values(['driver', 'season', 'round']).reset_index(drop=True)
    
    # For each window size, calculate rolling average
    for window in windows:
        col_name = f'avg_race_pos_{window}_races'
        print(f"\nCalculating {col_name}...")
        
        # Group by driver and calculate rolling mean
        # min_periods=1 ensures we get values even for drivers with fewer races
        df[col_name] = (
            df.groupby('driver')['race_pos']
            .rolling(window=window, min_periods=1)
            .mean()
            .reset_index(level=0, drop=True)
        )
        
        # CRITICAL: Shift by 1 to use only PAST races (avoid data leakage)
        # This ensures the rolling average for a race only includes races BEFORE it
        df[col_name] = df.groupby('driver')[col_name].shift(1)
        
        # Count how many non-null values we have
        non_null_count = df[col_name].notna().sum()
        print(f"  ✓ Created {col_name} with {non_null_count} valid values")

    
    # Show a sample of the results
    print("\nSample of rolling averages (first 25 rows with valid data):")
    sample_cols = ['season', 'race_name', 'driver', 'race_pos', 
                   'avg_race_pos_3_races', 'avg_race_pos_5_races', 
                   'avg_race_pos_7_races']
    available_cols = [col for col in sample_cols if col in df.columns]
    sample_df = df[available_cols].dropna(subset=['race_pos']).head(25)
    
    print(sample_df.to_string(index=False))
    
    return df


def main(start_year: int, end_year: int, start_race_name: str = None, end_race_name: str = None, output_csv: str = "qualifying_to_race_performance.csv"):
    """
    Collect practice, qualifying, and race data.
    """
    print(f"Collecting data from {start_year} to {end_year}...")
    
    all_data = []
    
    # Process each year
    for year in range(start_year, end_year + 1):
        print(f"Processing {year} season...")
        
        schedule = fastf1.get_event_schedule(year)
        
        # Filter races for the first year (start from start_race_name)
        if year == start_year and start_race_name:
            start_idx = schedule[schedule['EventName'] == start_race_name].index
            if len(start_idx) > 0:
                schedule = schedule.loc[start_idx[0]:]
                print(f"Starting from race: {start_race_name}")
            else:
                print(f"Warning: Start race '{start_race_name}' not found in {year} schedule")
        
        # Filter races for the last year (end at end_race_name)
        if year == end_year and end_race_name:
            end_idx = schedule[schedule['EventName'] == end_race_name].index
            if len(end_idx) > 0:
                schedule = schedule.loc[:end_idx[0]]
                print(f"Ending at race: {end_race_name}")
            else:
                print(f"Warning: End race '{end_race_name}' not found in {year} schedule")
        
        # Get list of race names to process for this year
        race_rows = schedule[['EventName', 'Location']]
        race_names = race_rows['EventName'].tolist()
        race_display_map = dict(zip(race_rows['EventName'], race_rows['Location']))
        print("This is the race name: ", race_names)
        print(f"Processing {len(race_names)} races in {year}: {', '.join(race_names)}")
        
        # Process each race in this year
        for idx, race_name in enumerate(race_names, 1):
            print(f"\n[{year}] [{idx}/{len(race_names)}] Processing {race_name}...")
            
            try:
                # Collect practice data
                print(f" Collecting practice data...")
                practice_df = free_practice_performance(year, race_name)
                
                # Collect qualifying data
                print(f" Collecting qualifying data...")
                qualifying_df = qualifying_performance(year, race_name)
                
                # Collect race data
                print(f" Collecting race data...")
                race_df = race_performance(year, race_name)
                
                # Merge all dataframes on common keys (season, race_name, driver)
                # Start with practice data
                merged_df = practice_df.copy()
                
                # Merge qualifying data
                if not qualifying_df.empty:
                    # Drop team column from qualifying_df to avoid conflicts
                    qualifying_df_no_team = qualifying_df.drop(columns=['team'], errors='ignore')
                    merged_df = merged_df.merge(
                        qualifying_df_no_team,
                        on=['season', 'race_name', 'driver'],
                        how='outer',
                        suffixes=('', '_qual')
                    )
                    # Remove duplicate columns if any
                    merged_df = merged_df.loc[:, ~merged_df.columns.duplicated()]
                
                # Merge race data
                if not race_df.empty:
                    # Drop team column from race_df to avoid conflicts
                    race_df_no_team = race_df.drop(columns=['team'], errors='ignore')
                    merged_df = merged_df.merge(
                        race_df_no_team,
                        on=['season', 'race_name', 'driver'],
                        how='outer',
                        suffixes=('', '_race')
                    )
                    # Remove duplicate columns if any
                    merged_df = merged_df.loc[:, ~merged_df.columns.duplicated()]
                
                # Fill in missing team values from qualifying or race data if practice data didn't have it
                if 'team' not in merged_df.columns or merged_df['team'].isna().any():
                    # Try to get team from qualifying results
                    if not qualifying_df.empty:
                        team_lookup = qualifying_df.set_index('driver')['team'].to_dict()
                        if 'team' not in merged_df.columns:
                            merged_df['team'] = merged_df['driver'].map(team_lookup)
                        else:
                            merged_df['team'] = merged_df['team'].fillna(merged_df['driver'].map(team_lookup))
                
                all_data.append(merged_df)
                print(f" Successfully collected data for {race_name}")
                
            except Exception as e:
                print(f" Error processing {race_name}: {e}")
                import traceback
                traceback.print_exc()
                continue
    
    # Combine all races into one dataframe
    if not all_data:
        print("\nNo data collected!")
        return pd.DataFrame()
    
    final_df = pd.concat(all_data, ignore_index=True)
    
    # Sort by season, race_name (round), and driver
    final_df = final_df.sort_values(['season', 'race_name', 'driver']).reset_index(drop=True)
    
    final_df["qualifying_pos"] = pd.to_numeric(
        final_df.get("Qualifying_Final_Grid_Position", np.nan),
        errors="coerce"
        )

    # Race position column name differs by weekend type; combine whichever exists
    if "Race_Finishing_Position" in final_df.columns and "race_final_position" in final_df.columns:
        final_df["race_pos"] = final_df["Race_Finishing_Position"].combine_first(final_df["race_final_position"])
    elif "Race_Finishing_Position" in final_df.columns:
        final_df["race_pos"] = final_df["Race_Finishing_Position"]
    elif "race_final_position" in final_df.columns:
        final_df["race_pos"] = final_df["race_final_position"]
    else:
        final_df["race_pos"] = np.nan

    final_df["race_pos"] = pd.to_numeric(final_df["race_pos"], errors="coerce")

    # Positive = gained places (qualified 10th, finished 6th => +4)
    final_df["position_gain_from_quali_to_race"] = final_df["qualifying_pos"] - final_df["race_pos"]
    
    final_df = calculate_rolling_avg_positions(final_df, windows=[3, 5, 7])
    
    # Export to CSV
    final_df.to_csv(output_csv, index=False)
    print(f" Data exported to {output_csv}")
    print(f" Total rows: {len(final_df)}")
    print(f" Total columns: {len(final_df.columns)}")
    print(f" Years covered: {final_df['season'].unique()}")
    
    return final_df
    
    


if __name__ == "__main__":
    # df1 = free_practice_performance(2025, "Austin")
    # with pd.option_context('display.max_rows', None, 'display.max_columns', None):  # more options can be specified also
    #     print(df1)
    
    # print("--------------------------------")
    
    # df2 = free_practice_performance(2025, "Melbourne")
    # with pd.option_context('display.max_rows', None, 'display.max_columns', None):  # more options can be specified also
    #     print(df2)
    
    # df3 = qualifying_performance(2025, "Austin")
    # df4 = qualifying_performance(2025, "Melbourne")
    
    # df5 = qualifying_performance(2025, "Abu Dhabi")
    # df6 = race_performance(2025, "Melbourne")
    
    df7 = main(2024, 2025, start_race_name="Melbourne", end_race_name="Abu Dhabi")
    
    # pd.set_option('display.max_rows', None)
    # pd.set_option('display.max_columns', None)
    # pd.set_option('display.max_colwidth', None)

    # print(df5)
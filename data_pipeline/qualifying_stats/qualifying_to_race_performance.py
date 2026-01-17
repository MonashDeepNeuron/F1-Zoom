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
    # Cache the round number 
    race_number = get_round_from_race_name(race_name, season)
    
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
    driver_to_number = {
        "VER": 1, "NOR": 4, "SAI": 55, "PIA": 81, "ALO": 14,
        "RUS": 63, "HAM": 44, "LEC": 16, "STR": 18, "TSU": 22,
        "ALB": 23, "HUL": 27, "GAS": 10, "OCO": 31, "PER": 11,
        "RIC": 3, "SAR": 2, "BOT": 77, "ZHO": 24, "MAG": 20,
        "ANT": 12, "BEA": 87, "DOO": 7, "COL": 43, "LAW": 30,
        "BOR": 5, "HAD": 6
    }
    
    if driver_number not in driver_to_number.values() and driver_number == 38 or driver_number not in driver_to_number.values() and driver_number == 50:
        return "BEA"
    
    if driver_number not in driver_to_number.values() and driver_number == 61:
        return "DOO"
    
    for driver, number in driver_to_number.items():
        if number == driver_number:
            return driver
    return "Unknown"

def format_lap_time(lap_time) -> str:
    """Format Timedelta lap time as M:SS.mmm (e.g., 1:33.648). Returns np.nan if input is NaN/None."""
    if lap_time is None or pd.isna(lap_time):
        return np.nan
    total_seconds = lap_time.total_seconds()
    minutes = int(total_seconds // 60)
    seconds = int(total_seconds % 60)
    milliseconds = int((total_seconds % 1) * 1000)
    return f"{minutes}:{seconds:02d}.{milliseconds:03d}"


def sprint_or_standard_weekend(race_name: str) -> bool:
    # return True if it is a sprint weekend
    
    sprint_weekend_race_names = ['Shanghai', 'Miami', 'Spa-Francorchamps', 'Austin', 'Sao Paulo', 'Lusail']
    
    if race_name in sprint_weekend_race_names:
        return True
    else:
        return False


def free_practice_performance(year: int, race_name: str) -> pd.DataFrame:
    
    rows = []
    
    if not sprint_or_standard_weekend(race_name):
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
    
    if not sprint_or_standard_weekend(race_name):
        
        # only a standard qualifying
        qualifying_session = fastf1.get_session(year, race_name, "Qualifying")
        qualifying_session.load()
        qualifying_results = qualifying_session.results
        
        for idx, row in qualifying_results.iterrows():
            driver_code = row['Abbreviation']
            
            rows.append({
                "season": year,
                "race_name": race_name,
                "driver": driver_code,
                "team": row['TeamName'],
                "Qualifying_Final_Grid_Position": int(row['Position']) if pd.notna(row['Position']) else np.nan,
                "Q1_fastest_lap": format_lap_time(row.get('Q1', pd.NaT)), 
                "Q2_fastest_lap": format_lap_time(row.get('Q2', pd.NaT)), 
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
        
        sprint_qualifying_dict = {}
        for idx, row in sprint_qualifying_results.iterrows():
            driver_code = row['Abbreviation']
            sprint_qualifying_dict[driver_code] = {
                "team": row['TeamName'],
                "Sprint_Qualifying_Final_Grid_Position": int(row['Position']) if pd.notna(row['Position']) else np.nan,
                "SQ1_fastest_lap": format_lap_time(row.get('Q1', pd.NaT)), 
                "SQ2_fastest_lap": format_lap_time(row.get('Q2', pd.NaT)), 
                "SQ3_fastest_lap": format_lap_time(row.get('Q3', pd.NaT))
            }
        
        
        for idx, row in qualifying_results.iterrows():
            driver_code = row['Abbreviation']
            sprint_data = sprint_qualifying_dict.get(driver_code, {})
            
            rows.append({
                "season": year,
                "race_name": race_name,
                "driver": driver_code,
                "team": sprint_data.get("team", row['TeamName']),  # Use sprint qual team, fallback to qual team
                "Sprint_Qualifying_Final_Grid_Position": sprint_data.get("Sprint_Qualifying_Final_Grid_Position", np.nan),
                "SQ1_fastest_lap": sprint_data.get("SQ1_fastest_lap", np.nan), 
                "SQ2_fastest_lap": sprint_data.get("SQ2_fastest_lap", np.nan), 
                "SQ3_fastest_lap": sprint_data.get("SQ3_fastest_lap", np.nan),
                "Qualifying_Final_Grid_Position": int(row['Position']) if pd.notna(row['Position']) else np.nan,
                "Q1_fastest_lap": format_lap_time(row.get('Q1', pd.NaT)), 
                "Q2_fastest_lap": format_lap_time(row.get('Q2', pd.NaT)), 
                "Q3_fastest_lap": format_lap_time(row.get('Q3', pd.NaT))
            })
        
    return pd.DataFrame(rows)
    

def race_performance(year: int, race_name: str) -> pd.DataFrame:
    
    rows = []
    
    if not sprint_or_standard_weekend(race_name):
        
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
                    merged_df = merged_df.merge(
                        qualifying_df,
                        on=['season', 'race_name', 'driver', 'team'],
                        how='outer',
                        suffixes=('', '_qual')
                    )
                    # Remove duplicate columns if any
                    merged_df = merged_df.loc[:, ~merged_df.columns.duplicated()]
                
                # Merge race data
                if not race_df.empty:
                    merged_df = merged_df.merge(
                        race_df,
                        on=['season', 'race_name', 'driver', 'team'],
                        how='outer',
                        suffixes=('', '_race')
                    )
                    # Remove duplicate columns if any
                    merged_df = merged_df.loc[:, ~merged_df.columns.duplicated()]
                
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
    
    # df5 = race_performance(2025, "Austin")
    # df6 = race_performance(2025, "Melbourne")
    
    df7 = main(2024, 2025, start_race_name="Melbourne", end_race_name="Melbourne")
    
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    pd.set_option('display.max_colwidth', None)

    print(df7)
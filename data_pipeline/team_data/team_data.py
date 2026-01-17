import fastf1.ergast
import fastf1
import pandas as pd

def normalize_team_name(team_name):
    """Normalize team names for consistent matching."""
    team_map = {
        'Alpine': 'alpine',
        'Aston Martin': 'aston_martin',
        'Ferrari': 'ferrari',
        'Haas F1 Team': 'haas',
        'Kick Sauber': 'sauber',
        'McLaren': 'mclaren',
        'Mercedes': 'mercedes',
        'RB': 'rb',
        'Red Bull Racing': 'red_bull',
        'Williams': 'williams',
        'Alfa Romeo': 'alfa',
        'AlphaTauri': 'alphatauri'
    }
    return team_map.get(team_name, team_name.lower().replace(' ', '_'))


def get_driver_pitstop_averages(year, race_name=None, team=None):    
    """Collect average pit stop times for each driver in each race."""
    ergast = fastf1.ergast.Ergast()
    schedule = ergast.get_race_schedule(season=year)
    
    if race_name:
        schedule = schedule[schedule['raceName'] == race_name]
    
    results = []
    
    for idx, race in schedule.iterrows():
        round_number = race['round']
        race_name_current = race['raceName']
        
        try:
            pit_stops_response = ergast.get_pit_stops(season=year, round=round_number)
            pit_stops = pit_stops_response.content[0]
            
            if len(pit_stops) == 0:
                continue
            
            race_results_response = ergast.get_race_results(season=year, round=round_number)
            race_results = race_results_response.content[0]
            
            # Get driver info including code
            driver_info = race_results[['driverId', 'constructorId', 'code']].drop_duplicates()
            
            pit_stops_with_info = pit_stops.merge(
                driver_info, 
                on='driverId', 
                how='left'
            )
            
            pit_stops_with_info['duration_seconds'] = pit_stops_with_info['duration'].dt.total_seconds()
            
            driver_averages = pit_stops_with_info.groupby(['driverId', 'constructorId', 'code']).agg({
                'duration_seconds': 'mean',  
                'stop': 'count'
            }).reset_index()
            
            for _, row in driver_averages.iterrows():
                results.append({
                    'year': year,
                    'race_name': race_name_current,
                    'team': row['constructorId'],
                    'driver': row['code'],
                    'average_pit_stop_time': row['duration_seconds'],
                    'num_pit_stops': row['stop']
                })
        
        except Exception as e:
            print(f"Error processing {race_name_current}: {e}")
            continue
    
    return pd.DataFrame(results)


def get_driver_dnf_data_fastf1(year, race_name=None, team=None):
    """Collect DNF data for each driver in each race."""
    schedule = fastf1.get_event_schedule(year)
    schedule = schedule[schedule['EventFormat'] != 'testing']
    
    if race_name:
        schedule = schedule[schedule['EventName'] == race_name]
    
    results = []
    
    for idx, event in schedule.iterrows():
        race_name_current = event['EventName']
        round_number = event['RoundNumber']
        
        if pd.isna(round_number):
            continue
        
        try:
            session = fastf1.get_session(year, round_number, 'R')
            session.load()
            session_results = session.results
            
            if session_results is None or len(session_results) == 0:
                continue
            
            for driver_idx, driver_result in session_results.iterrows():
                status = driver_result['Status']
                classified_position = driver_result['ClassifiedPosition']
                
                is_dnf = False
                dnf_reason = None
                
                if pd.notna(status):
                    if status != 'Finished' and not status.startswith('+'):
                        is_dnf = True
                        dnf_reason = status
                
                if pd.notna(classified_position):
                    if classified_position in ['R', 'D', 'E', 'W', 'F', 'N']:
                        is_dnf = True
                        if dnf_reason is None:
                            dnf_reason = f"Not Classified ({classified_position})"
                
                if not is_dnf:
                    dnf_reason = status if pd.notna(status) else 'Finished'
                
                # Normalize team name for consistent matching
                normalized_team = normalize_team_name(driver_result['TeamName'])
                
                results.append({
                    'year': year,
                    'race_name': race_name_current,
                    'team': normalized_team,
                    'driver': driver_result['Abbreviation'],  # Use abbreviation instead of full name
                    'dnf': is_dnf,
                    'dnf_reason': dnf_reason
                })
        
        except Exception as e:
            print(f"Error processing {race_name_current}: {e}")
            continue
    
    return pd.DataFrame(results)


def main(start_year, start_race, end_year, end_race, output_csv):
    """
    Collect F1 data for a range of races and save to CSV.
    
    Parameters:
    -----------
    start_year : int
    start_race : str (e.g., 'Bahrain Grand Prix')
    end_year : int
    end_race : str (e.g., 'Abu Dhabi Grand Prix')
    output_csv : str
    """
    
    all_pitstop = []
    all_dnf = []
    ergast = fastf1.ergast.Ergast()
    
    for year in range(start_year, end_year + 1):
        print(f"\nProcessing {year}...")
        schedule = ergast.get_race_schedule(season=year)
        
        # Find start and end indices
        start_idx = 0 if year != start_year else schedule[schedule['raceName'] == start_race].index[0]
        end_idx = len(schedule) - 1 if year != end_year else schedule[schedule['raceName'] == end_race].index[0]
        
        races = schedule.loc[start_idx:end_idx]
        
        for idx, race in races.iterrows():
            print(f"  {race['raceName']}...")
            all_pitstop.append(get_driver_pitstop_averages(year, race['raceName']))
            all_dnf.append(get_driver_dnf_data_fastf1(year, race['raceName']))
    
    # Combine and merge
    pitstop_df = pd.concat(all_pitstop, ignore_index=True)
    dnf_df = pd.concat(all_dnf, ignore_index=True)
    
    # Merge on year, race_name, team, and driver
    combined = pitstop_df.merge(
        dnf_df, 
        on=['year', 'race_name', 'team', 'driver'], 
        how='outer'
    )
    
    # Sort by year, race, team, driver
    combined = combined.sort_values(['year', 'race_name', 'team', 'driver']).reset_index(drop=True)
    
    combined.to_csv(output_csv, index=False)
    
    print(f"\nSaved {len(combined)} records to {output_csv}")
    print(f"Races: {combined['race_name'].nunique()}")
    print(f"Teams: {combined['team'].nunique()}")
    print(f"Drivers: {combined['driver'].nunique()}")
    
    return combined


# Example usage:
if __name__ == "__main__":
    # Full 2024 season
    df = main(2024, 'Bahrain Grand Prix', 2024, 'Abu Dhabi Grand Prix', 'team_data.csv')

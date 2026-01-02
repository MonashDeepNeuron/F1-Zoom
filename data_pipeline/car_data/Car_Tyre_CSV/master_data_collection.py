import pandas as pd
import os
from pathlib import Path

def load_all_data(csv_dir: str = "Car_Tyre_CSV") -> dict:
    """Load all CSV files into a dictionary of DataFrames."""
    csv_files = {
        'car_race_summary': 'car_race_summary.csv',
        'driver_race_summary': 'driver_race_summary.csv',
        'lap_by_lap': 'lap_by_lap_data.csv',
        'lap_by_lap_track_status': 'lap_by_lap_data_track_status.csv',
        'qualifying_to_race': 'qualifying_to_race_performance.csv',
        'stint_analysis': 'stint_analysis.csv',
        'track_overtaking': 'track_overtaking_data.csv'
    }
    
    dataframes = {}
    for name, filename in csv_files.items():
        filepath = Path(csv_dir) / filename
        dataframes[name] = pd.read_csv(filepath)
        print(f"Loaded {name}: {len(dataframes[name])} rows")
    
    return dataframes


def create_master_dataframe(dataframes: dict) -> pd.DataFrame:
    """Create a unified master DataFrame by merging all data sources."""
    
    # Mapping from circuit/race names to official GP names for track data
    circuit_to_gp = {
        'Sakhir': 'Bahrain Grand Prix',
        'Jeddah': 'Saudi Arabian Grand Prix',
        'Melbourne': 'Australian Grand Prix',
        'Suzuka': 'Japanese Grand Prix',
        'Shanghai': 'Chinese Grand Prix',
        'Miami': 'Miami Grand Prix',
        'Imola': 'Emilia Romagna Grand Prix',
        'Monaco': 'Monaco Grand Prix',
        'Monte Carlo': 'Monaco Grand Prix',
        'Montreal': 'Canadian Grand Prix',
        'Barcelona': 'Spanish Grand Prix',
        'Catalunya': 'Spanish Grand Prix',
        'Spielberg': 'Austrian Grand Prix',
        'Silverstone': 'British Grand Prix',
        'Budapest': 'Hungarian Grand Prix',
        'Hungaroring': 'Hungarian Grand Prix',
        'Spa-Francorchamps': 'Belgian Grand Prix',
        'Zandvoort': 'Dutch Grand Prix',
        'Monza': 'Italian Grand Prix',
        'Baku': 'Azerbaijan Grand Prix',
        'Singapore': 'Singapore Grand Prix',
        'Austin': 'United States Grand Prix',
        'Mexico City': 'Mexico City Grand Prix',
        'São Paulo': 'São Paulo Grand Prix',
        'Las Vegas': 'Las Vegas Grand Prix',
        'Lusail': 'Qatar Grand Prix',
        'Yas Marina': 'Abu Dhabi Grand Prix',
        'Yas Marina Circuit': 'Abu Dhabi Grand Prix',
        # Common variations
        'Spa': 'Belgian Grand Prix',
        'COTA': 'United States Grand Prix',
        'Interlagos': 'São Paulo Grand Prix',
    }
    
    # Start with lap-by-lap data (most granular)
    master = dataframes['lap_by_lap_track_status'].copy()
    
    # Add GP name column for track data merge
    master['gp_name'] = master['race_name'].map(circuit_to_gp)
    
    # Merge stint analysis data
    stint_cols = ['season', 'race_name', 'driver', 'stint_index', 'compound',
                  'start_lap', 'end_lap', 'stint_length_laps', 'pit_ended_stint',
                  'avg_laptime', 'best_laptime', 'laptime_slope_per_lap',
                  'clean_air_avg_laptime']
    stint_data = dataframes['stint_analysis'][stint_cols].copy()
    stint_data.columns = ['season', 'race_name', 'driver', 'stint_index', 
                          'stint_compound', 'stint_start_lap', 'stint_end_lap',
                          'stint_length', 'stint_pit_ended', 'stint_avg_laptime',
                          'stint_best_laptime', 'stint_deg_slope', 'stint_clean_air_avg']
    
    master = master.merge(
        stint_data,
        on=['season', 'race_name', 'driver', 'stint_index'],
        how='left'
    )
    
    # Merge driver race summary data
    driver_cols = ['season', 'driver', 'race_name', 'finishing_position', 
                   'race_status', 'avg_race_pace', 'clean_air_avg_race_pace',
                   'top_speed', 'cornering_speed', 'top_speed_rank', 
                   'corner_speed_rank', 'drag_index']
    driver_data = dataframes['driver_race_summary'][driver_cols].copy()
    driver_data.columns = ['season', 'driver', 'race_name', 'race_finish_pos',
                           'race_status', 'driver_avg_pace', 'driver_clean_air_pace',
                           'driver_top_speed', 'driver_corner_speed', 
                           'driver_top_speed_rank', 'driver_corner_speed_rank',
                           'driver_drag_index']
    
    master = master.merge(
        driver_data,
        on=['season', 'race_name', 'driver'],
        how='left'
    )
    
    # Merge track overtaking data using the GP name mapping
    track_data = dataframes['track_overtaking'].copy()
    track_data.columns = ['gp_name', 'track_score', 'track_avg_overtakes',
                          'track_sc_pct', 'track_vsc_pct', 'track_red_pct']
    
    master = master.merge(
        track_data,
        on='gp_name',
        how='left'
    )
    
    # Merge qualifying to race performance data
    # This data uses GP names, so we merge on gp_name + season + driver
    quali_data = dataframes['qualifying_to_race'].copy()
    quali_cols_to_use = ['season', 'race_name', 'driver', 
                         'fp1_pos', 'fp1_time_fastest_lap',
                         'fp2_pos', 'fp2_time_fastest_lap',
                         'fp3_pos', 'fp3_time_fastest_lap',
                         'Qualifying_Final_Grid_Position',
                         'Q1_fastest_lap', 'Q2_fastest_lap', 'Q3_fastest_lap']
    quali_data = quali_data[quali_cols_to_use].copy()
    quali_data.columns = ['season', 'gp_name', 'driver',
                          'fp1_pos', 'fp1_time',
                          'fp2_pos', 'fp2_time',
                          'fp3_pos', 'fp3_time',
                          'quali_grid_pos',
                          'q1_time', 'q2_time', 'q3_time']
    
    # Drop duplicates (some drivers have multiple entries per race due to team name variations)
    quali_data = quali_data.drop_duplicates(subset=['season', 'gp_name', 'driver'], keep='first')
    
    master = master.merge(
        quali_data,
        on=['season', 'gp_name', 'driver'],
        how='outer'
    )
    
    # For rows that came from qualifying data without lap-by-lap data,
    # fill in the race_name using the circuit name (reverse mapping from GP name)
    # Use the primary circuit name for each GP (first key that maps to each GP)
    gp_to_circuit = {
        'Bahrain Grand Prix': 'Sakhir',
        'Saudi Arabian Grand Prix': 'Jeddah',
        'Australian Grand Prix': 'Melbourne',
        'Japanese Grand Prix': 'Suzuka',
        'Chinese Grand Prix': 'Shanghai',
        'Miami Grand Prix': 'Miami',
        'Emilia Romagna Grand Prix': 'Imola',
        'Monaco Grand Prix': 'Monte Carlo',
        'Canadian Grand Prix': 'Montreal',
        'Spanish Grand Prix': 'Catalunya',
        'Austrian Grand Prix': 'Spielberg',
        'British Grand Prix': 'Silverstone',
        'Hungarian Grand Prix': 'Hungaroring',
        'Belgian Grand Prix': 'Spa-Francorchamps',
        'Dutch Grand Prix': 'Zandvoort',
        'Italian Grand Prix': 'Monza',
        'Azerbaijan Grand Prix': 'Baku',
        'Singapore Grand Prix': 'Singapore',
        'United States Grand Prix': 'Austin',
        'Mexico City Grand Prix': 'Mexico City',
        'São Paulo Grand Prix': 'Interlagos',
        'Las Vegas Grand Prix': 'Las Vegas',
        'Qatar Grand Prix': 'Lusail',
        'Abu Dhabi Grand Prix': 'Yas Marina Circuit',
    }
    
    if 'race_name' in master.columns:
        # Map gp_name to circuit name for rows without race_name
        master['race_name'] = master['race_name'].fillna(master['gp_name'].map(gp_to_circuit))
        # Fallback to gp_name if no mapping exists
        master['race_name'] = master['race_name'].fillna(master['gp_name'])
    
    return master


def save_combined_data(master_df: pd.DataFrame, 
                       dataframes: dict,
                       output_dir: str = "Car_Tyre_CSV"):
    """Save the combined data to CSV and Excel (or CSVs if openpyxl not available)."""
    
    output_path = Path(output_dir)
    
    # Save master DataFrame to CSV
    master_csv = output_path / "master_combined_data.csv"
    master_df.to_csv(master_csv, index=False)
    print(f"Saved master CSV: {master_csv} ({len(master_df)} rows)")
    
    # Try to save as Excel, fall back to CSVs if openpyxl not installed
    try:
        import openpyxl  # Check if available
        excel_path = output_path / "all_f1_data.xlsx"
        with pd.ExcelWriter(excel_path, engine='openpyxl') as writer:
            for name, df in dataframes.items():
                # Excel sheet names have 31 char limit
                sheet_name = name[:31]
                df.to_excel(writer, sheet_name=sheet_name, index=False)
            master_df.to_excel(writer, sheet_name='master_combined', index=False)
        print(f"Saved Excel workbook: {excel_path}")
        
    except ImportError:
        print("Note: openpyxl not installed, skipping Excel export.")
        print("To enable Excel export, run: pip install openpyxl")
        print("All data is available in the master CSV file.")


def main():
    """Main function to collect and combine all F1 data."""
    
    csv_dir = "Car_Tyre_CSV"
    
    print("=" * 60)
    print("F1 Data Collection & Combination Tool")
    print("=" * 60)
    
    # Step 1: Load all CSV files
    print("\n[1/3] Loading all CSV files...")
    dataframes = load_all_data(csv_dir)
    
    # Step 2: Create master merged DataFrame
    print("\n[2/3] Creating master combined DataFrame...")
    master_df = create_master_dataframe(dataframes)
    print(f"Master DataFrame created: {len(master_df)} rows, {len(master_df.columns)} columns")
    
    # Step 3: Save outputs
    print("\n[3/3] Saving combined data...")
    save_combined_data(master_df, dataframes, csv_dir)
    
    print("\n" + "=" * 60)
    print("Data collection complete!")
    print("=" * 60)
    
    # Return for interactive use
    return master_df, dataframes


if __name__ == "__main__":
    master_df, all_dataframes = main()
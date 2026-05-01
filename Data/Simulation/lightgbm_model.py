# pip install lightgbm scikit-learn pandas numpy supabase python-dotenv

import argparse
import os
import sys

import pandas as pd
import numpy as np
import re
import joblib
from pathlib import Path
from lightgbm import LGBMRanker

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")
except ImportError:
    pass

DRIVER_TEAM_FALLBACK = {
    "RUS": "Mercedes", "ANT": "Mercedes",
    "LEC": "Ferrari", "HAM": "Ferrari",
    "NOR": "McLaren", "PIA": "McLaren",
    "OCO": "Haas", "BEA": "Haas",
    "VER": "Red Bull Racing", "TSU": "Red Bull Racing", "HAD": "Red Bull Racing",
    "LAW": "Racing Bulls", "LIN": "Racing Bulls",
    "GAS": "Alpine", "COL": "Alpine",
    "HUL": "Audi", "BOR": "Audi",
    "SAI": "Williams", "ALB": "Williams",
    "PER": "Cadillac", "BOT": "Cadillac",
    "ALO": "Aston Martin", "STR": "Aston Martin",
}

TEAM_NAME_ALIASES = {
    "Haas F1 Team": "Haas",
    "Oracle Red Bull Racing": "Red Bull Racing",
    "Red Bull": "Red Bull Racing",
    "RB": "Racing Bulls",
    "RB F1 Team": "Racing Bulls",
    "Visa Cash App RB": "Racing Bulls",
    "Visa Cash App Racing Bulls F1 Team": "Racing Bulls",
    "Kick Sauber": "Audi",
    "Stake F1 Team Kick Sauber": "Audi",
    "Sauber": "Audi",
    "Cadillac F1 Team": "Cadillac",
    "Aston Martin Aramco": "Aston Martin",
    "Aston Martin Aramco Mercedes": "Aston Martin",
}

# ============================================================================
# CONFIGURATION
# ============================================================================

parser = argparse.ArgumentParser(description="F1 Race Prediction Model")
parser.add_argument("--season", type=int, default=2026)
parser.add_argument("--race-name", type=str, default="Japanese Grand Prix")
parser.add_argument(
    "--from-supabase", action="store_true",
    help="Load training data from Supabase instead of CSV",
)
parser.add_argument(
    "--season-filter", type=int, default=None,
    help="Restrict training data to a single season (e.g. 2026)",
)
parser.add_argument(
    "--auto", action="store_true",
    help="Auto-detect the next upcoming race from Supabase (implies --from-supabase)",
)
args = parser.parse_args()

SCRIPT_DIR = Path(__file__).parent.resolve()
DATA_PATH = SCRIPT_DIR / "../../data_pipeline/car_data/Car_Tyre_CSV/master_combined_data.csv"
DATA_PATH = DATA_PATH.resolve()

# Resolved after helper functions are defined (see bottom of CONFIGURATION block)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def time_to_seconds(time_value):
    """
    Convert time strings or numbers to float seconds.
    Handles formats: 'M:SS.mmm', 'SS.mmm', or numeric values.
    """
    if pd.isna(time_value):
        return np.nan
    
    if isinstance(time_value, (int, float)):
        return float(time_value)
    
    time_str = str(time_value).strip()
    if time_str in ["", "None", "nan"]:
        return np.nan
    
    # Match M:SS(.mmm) or SS(.mmm)
    match = re.match(r"^(?:(\d+):)?(\d+(?:\.\d+)?)$", time_str)
    if not match:
        return np.nan
    
    minutes = float(match.group(1)) if match.group(1) else 0.0
    seconds = float(match.group(2))
    return 60.0 * minutes + seconds


def canonicalize_team_name(team_name):
    if pd.isna(team_name):
        return np.nan
    team_str = str(team_name).strip()
    if not team_str:
        return np.nan
    return TEAM_NAME_ALIASES.get(team_str, team_str)


def resolve_team_name(driver_code, team_name):
    canonical = canonicalize_team_name(team_name)
    if pd.notna(canonical):
        return canonical
    return DRIVER_TEAM_FALLBACK.get(driver_code)


def add_driver_history_features(df):
    """
    Add rolling historical features for each driver.
    Uses only previous races to avoid data leakage.
    """
    df = df.sort_values(["season", "race_id", "driver"]).reset_index(drop=True)
    
    grouped = df.groupby("driver", sort=False)
    
    # Lag features (previous race only)
    df["hist_finish_lag1"] = grouped["race_finish_pos"].shift(1)
    df["hist_grid_lag1"] = grouped["grid_pos"].shift(1)
    
    # Rolling averages (3 and 5 race windows)
    df["hist_finish_roll3"] = (
        grouped["race_finish_pos"]
        .shift(1)
        .rolling(3, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    df["hist_finish_roll5"] = (
        grouped["race_finish_pos"]
        .shift(1)
        .rolling(5, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    df["hist_grid_roll3"] = (
        grouped["grid_pos"]
        .shift(1)
        .rolling(3, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    df["hist_grid_roll5"] = (
        grouped["grid_pos"]
        .shift(1)
        .rolling(5, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    df["hist_q3_roll3"] = (
        grouped["q3_time"]
        .shift(1)
        .rolling(3, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    df["hist_q3_roll5"] = (
        grouped["q3_time"]
        .shift(1)
        .rolling(5, min_periods=1)
        .mean()
        .reset_index(level=0, drop=True)
    )
    
    return df


def load_training_data_from_supabase(season_filter: int | None = None):
    """
    Load training data from Supabase.

    Returns a DataFrame whose column names match the CSV format so the
    existing COLUMN_MAPPING works without changes.
    """
    from supabase import create_client

    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )

    result = (
        client.table("driver_race_entries")
        .select(
            "*, "
            "drivers(driver_code), "
            "teams(team_name), "
            "race_events(season, round, grand_prix_name)"
        )
        .limit(5000)
        .execute()
    )

    rows = []
    for entry in result.data:
        drv = entry.get("drivers") or {}
        team = entry.get("teams") or {}
        race = entry.get("race_events") or {}

        season = race.get("season")
        if season_filter is not None and season != season_filter:
            continue

        gp_name = race.get("grand_prix_name")

        rows.append({
            # Identifiers
            "season": season,
            "race_name": gp_name,
            "gp_name": gp_name,
            "round": race.get("round"),
            "driver": drv.get("driver_code"),
            "team_x": resolve_team_name(drv.get("driver_code"), team.get("team_name")),
            # Practice
            "fp1_pos": entry.get("fp1_pos"),
            "fp1_time_fastest_lap": entry.get("fp1_time_fastest_lap"),
            "fp2_pos": entry.get("fp2_pos"),
            "fp2_time_fastest_lap": entry.get("fp2_time_fastest_lap"),
            "fp3_pos": entry.get("fp3_pos"),
            "fp3_time_fastest_lap": entry.get("fp3_time_fastest_lap"),
            # Qualifying (DB snake_case → CSV mixed-case)
            "Qualifying_Final_Grid_Position": entry.get("qualifying_final_grid_pos"),
            "Q1_time_seconds": entry.get("q1_time_seconds"),
            "Q2_time_seconds": entry.get("q2_time_seconds"),
            "Q3_time_seconds": entry.get("q3_time_seconds"),
            "Q1_position": entry.get("q1_position"),
            "Q2_position": entry.get("q2_position"),
            "Q3_position": entry.get("q3_position"),
            # Race
            "Race_Finishing_Position": entry.get("race_finish_pos"),
            "race_status": entry.get("race_status"),
            # Pace metrics
            "driver_avg_pace": entry.get("driver_avg_pace"),
            "driver_clean_air_pace": entry.get("driver_clean_air_pace"),
            "driver_grid_avg_pace": entry.get("driver_grid_avg_pace"),
            "driver_pace_delta_to_grid": entry.get("driver_pace_delta_to_grid"),
            "driver_pace_zscore_vs_grid": entry.get("driver_pace_zscore_vs_grid"),
            "driver_pace_score_vs_grid": entry.get("driver_pace_score_vs_grid"),
            "driver_pace_score_0_100": entry.get("driver_pace_score_0_100"),
            # Speed metrics
            "driver_top_speed": entry.get("driver_top_speed"),
            "driver_corner_speed": entry.get("driver_corner_speed"),
            "driver_top_speed_rank": entry.get("driver_top_speed_rank"),
            "driver_corner_speed_rank": entry.get("driver_corner_speed_rank"),
            "driver_drag_index": entry.get("driver_drag_index"),
            # Historical averages
            "avg_race_pos_3_races": entry.get("avg_race_pos_3_races"),
            "avg_race_pos_5_races": entry.get("avg_race_pos_5_races"),
            "avg_race_pos_7_races": entry.get("avg_race_pos_7_races"),
            "position_gain_from_quali_to_race": entry.get("position_gain_from_quali_to_race"),
        })

    return pd.DataFrame(rows)


def create_prediction_entries_from_supabase(season: int, race_name: str):
    """
    Create placeholder prediction entries for a future race by looking up
    all drivers registered for the given season.  Used when the target race
    hasn't happened yet and has no driver_race_entries rows.
    """
    from supabase import create_client

    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )

    drivers_result = client.table("drivers").select("driver_code").execute()
    teams_result = (
        client.table("teams")
        .select("team_name")
        .eq("season", season)
        .execute()
    )

    driver_codes = [d["driver_code"] for d in drivers_result.data]
    team_names = [t["team_name"] for t in teams_result.data]

    rows = []
    for code in driver_codes:
        team = DRIVER_TEAM_FALLBACK.get(code)
        if team is None or team not in team_names:
            continue
        rows.append({
            "season": season,
            "race_name": race_name,
            "gp_name": race_name,
            "driver": code,
            "team_x": team,
        })

    return pd.DataFrame(rows)


def upsert_predictions_to_supabase(results_df, season, race_name):
    """Upsert prediction results to the Supabase predictions table."""
    from supabase import create_client

    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )

    # Try grand_prix_name first (2026+), fall back to race_name for legacy data
    event_result = (
        client.table("race_events")
        .select("id")
        .eq("season", season)
        .eq("grand_prix_name", race_name)
        .limit(1)
        .execute()
    )
    if not event_result.data:
        print(f"WARNING: No race_event for {season} '{race_name}' — skipping Supabase upsert")
        return

    race_event_id = event_result.data[0]["id"]

    prediction_rows = []
    for _, row in results_df.iterrows():
        grid_pos = row.get("grid_pos")
        prediction_rows.append({
            "race_event_id": race_event_id,
            "driver_code": row["driver"],
            "team": resolve_team_name(row["driver"], row.get("team")),
            "predicted_position": int(row["predicted_position"]),
            "prediction_score": float(row["prediction_score"]),
            "grid_position": int(grid_pos) if pd.notna(grid_pos) else None,
        })

    client.table("predictions").upsert(
        prediction_rows, on_conflict="race_event_id,driver_code",
    ).execute()
    print(f"✓ Predictions upserted to Supabase for {season} {race_name}")


def get_next_race_from_supabase():
    """
    Find the next upcoming race that hasn't been processed by the data pipeline.
    Returns (season, grand_prix_name) or raises RuntimeError if none found.
    """
    from supabase import create_client
    from datetime import datetime, timezone

    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )

    now_utc = datetime.now(timezone.utc).isoformat()

    result = (
        client.table("race_sessions")
        .select("session_start_utc, race_events(season, round, grand_prix_name)")
        .eq("session_type", "race")
        .eq("data_fetched", False)
        .gte("session_start_utc", now_utc)
        .order("session_start_utc", desc=False)
        .limit(1)
        .execute()
    )

    if not result.data:
        raise RuntimeError(
            "No upcoming unfetched race sessions found in Supabase. "
            "Check that race_sessions is populated for the current season."
        )

    session = result.data[0]
    race_event = session.get("race_events") or {}
    season = race_event.get("season")
    gp_name = race_event.get("grand_prix_name")

    if not season or not gp_name:
        raise RuntimeError(f"Incomplete race_events data in result: {session}")

    return int(season), gp_name


def load_race_entries_from_supabase(season: int, race_name: str):
    """
    Load driver_race_entries for a specific race (by season + grand_prix_name).
    Returns a DataFrame in the same format as load_training_data_from_supabase(),
    or an empty DataFrame if no entries exist yet.

    Used as a fallback when the prediction race has no rows in the main training
    load (e.g., qualifying data was fetched after the training query ran).
    """
    from supabase import create_client

    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )

    event_result = (
        client.table("race_events")
        .select("id, season, round, grand_prix_name")
        .eq("season", season)
        .eq("grand_prix_name", race_name)
        .limit(1)
        .execute()
    )

    if not event_result.data:
        return pd.DataFrame()

    race_event = event_result.data[0]
    race_event_id = race_event["id"]

    result = (
        client.table("driver_race_entries")
        .select("*, drivers(driver_code), teams(team_name)")
        .eq("race_id", race_event_id)
        .execute()
    )

    if not result.data:
        return pd.DataFrame()

    rows = []
    for entry in result.data:
        drv = entry.get("drivers") or {}
        team = entry.get("teams") or {}

        rows.append({
            "season": race_event["season"],
            "race_name": race_event["grand_prix_name"],
            "gp_name": race_event["grand_prix_name"],
            "round": race_event["round"],
            "driver": drv.get("driver_code"),
            "team_x": resolve_team_name(drv.get("driver_code"), team.get("team_name")),
            "fp1_pos": entry.get("fp1_pos"),
            "fp1_time_fastest_lap": entry.get("fp1_time_fastest_lap"),
            "fp2_pos": entry.get("fp2_pos"),
            "fp2_time_fastest_lap": entry.get("fp2_time_fastest_lap"),
            "fp3_pos": entry.get("fp3_pos"),
            "fp3_time_fastest_lap": entry.get("fp3_time_fastest_lap"),
            "Qualifying_Final_Grid_Position": entry.get("qualifying_final_grid_pos"),
            "Q1_time_seconds": entry.get("q1_time_seconds"),
            "Q2_time_seconds": entry.get("q2_time_seconds"),
            "Q3_time_seconds": entry.get("q3_time_seconds"),
            "Q1_position": entry.get("q1_position"),
            "Q2_position": entry.get("q2_position"),
            "Q3_position": entry.get("q3_position"),
            "Race_Finishing_Position": entry.get("race_finish_pos"),
            "race_status": entry.get("race_status"),
            "driver_avg_pace": entry.get("driver_avg_pace"),
            "driver_clean_air_pace": entry.get("driver_clean_air_pace"),
            "driver_grid_avg_pace": entry.get("driver_grid_avg_pace"),
            "driver_pace_delta_to_grid": entry.get("driver_pace_delta_to_grid"),
            "driver_pace_zscore_vs_grid": entry.get("driver_pace_zscore_vs_grid"),
            "driver_pace_score_vs_grid": entry.get("driver_pace_score_vs_grid"),
            "driver_pace_score_0_100": entry.get("driver_pace_score_0_100"),
            "driver_top_speed": entry.get("driver_top_speed"),
            "driver_corner_speed": entry.get("driver_corner_speed"),
            "driver_top_speed_rank": entry.get("driver_top_speed_rank"),
            "driver_corner_speed_rank": entry.get("driver_corner_speed_rank"),
            "driver_drag_index": entry.get("driver_drag_index"),
            "avg_race_pos_3_races": entry.get("avg_race_pos_3_races"),
            "avg_race_pos_5_races": entry.get("avg_race_pos_5_races"),
            "avg_race_pos_7_races": entry.get("avg_race_pos_7_races"),
            "position_gain_from_quali_to_race": entry.get("position_gain_from_quali_to_race"),
        })

    return pd.DataFrame(rows)


def add_driver_history_features_single_race(pred_df, history_df):
    """
    Carry forward the most recent history columns from history_df into pred_df.
    Used when pred_df rows weren't present during the main add_driver_history_features()
    call (e.g., targeted fetch or placeholder creation).
    """
    hist_cols = [
        "hist_finish_roll3", "hist_finish_roll5",
        "hist_grid_roll3", "hist_grid_roll5",
        "hist_q3_roll3", "hist_q3_roll5",
    ]
    for drv in pred_df["driver"].unique():
        drv_history = history_df[history_df["driver"] == drv].sort_values("race_id")
        if drv_history.empty:
            continue
        last = drv_history.iloc[-1]
        idx = pred_df["driver"] == drv
        pred_df.loc[idx, "hist_finish_lag1"] = last.get("race_finish_pos")
        pred_df.loc[idx, "hist_grid_lag1"] = last.get("grid_pos")
        for col in hist_cols:
            if col in drv_history.columns:
                vals = drv_history[col].dropna()
                if len(vals):
                    pred_df.loc[idx, col] = vals.iloc[-1]
    return pred_df


# ============================================================================
# RESOLVE PRED_SEASON / PRED_RACE_NAME (after helpers are defined)
# ============================================================================

if args.auto:
    args.from_supabase = True
    PRED_SEASON, PRED_RACE_NAME = get_next_race_from_supabase()
    print(f"Auto-detected next race: {PRED_SEASON} {PRED_RACE_NAME}")
else:
    PRED_SEASON = args.season
    PRED_RACE_NAME = args.race_name


# ============================================================================
# LOAD AND PREPARE DATA
# ============================================================================

if args.from_supabase:
    print("Loading data from Supabase...")
    df_raw = load_training_data_from_supabase(season_filter=args.season_filter)
else:
    print("Loading data from CSV...")
    df_raw = pd.read_csv(DATA_PATH, low_memory=False)
    if args.season_filter is not None:
        df_raw = df_raw[df_raw["season"] == args.season_filter].copy()
        print(f"Filtered to season {args.season_filter}")

print(f"Raw data shape: {df_raw.shape}")
print(f"Columns: {list(df_raw.columns)}\n")

# Sort chronologically before creating race_id so that rolling history features
# flow in the correct calendar order (round 1 → round 2 → ...).
# The "round" column is populated when loading from Supabase.
if "round" in df_raw.columns:
    df_raw = df_raw.sort_values(["season", "round"], na_position="last").reset_index(drop=True)

# Create unique race identifier (insertion order = chronological order after sort)
race_key = df_raw[["season", "race_name"]].astype(str).agg(" | ".join, axis=1)
df_raw["race_key"] = race_key
df_raw["race_id"] = pd.factorize(df_raw["race_key"], sort=False)[0]

# ============================================================================
# COLUMN STANDARDIZATION
# ============================================================================

# Map your actual CSV columns to standardized names
COLUMN_MAPPING = {
    # Identifiers
    "season": "season",
    "race_name": "race_name",
    "gp_name": "gp_name",
    "driver": "driver",
    "team_x": "team",  # Using team_x (appears to be the main team column)
    
    # Track characteristics
    "track_score": "track_score",
    "track_avg_overtakes": "track_overtakes",
    "track_sc_pct": "track_sc_pct",
    "track_vsc_pct": "track_vsc_pct",
    "track_red_pct": "track_red_pct",
    
    # Practice sessions
    "fp1_pos": "fp1_pos",
    "fp1_time_fastest_lap": "fp1_time",
    "fp2_pos": "fp2_pos",
    "fp2_time_fastest_lap": "fp2_time",
    "fp3_pos": "fp3_pos",
    "fp3_time_fastest_lap": "fp3_time",
    
    # Qualifying
    "Qualifying_Final_Grid_Position": "grid_pos",
    "Q1_time_seconds": "q1_time",
    "Q2_time_seconds": "q2_time",
    "Q3_time_seconds": "q3_time",
    "Q1_position": "q1_pos",
    "Q2_position": "q2_pos",
    "Q3_position": "q3_pos",
    
    # Race results
    "Race_Finishing_Position": "race_finish_pos",
    "race_status": "race_status",
    
    # Driver performance metrics
    "driver_avg_pace": "pace_avg",
    "driver_clean_air_pace": "pace_clean_air",
    "driver_grid_avg_pace": "pace_grid_avg",
    "driver_pace_delta_to_grid": "pace_delta_grid",
    "driver_pace_zscore_vs_grid": "pace_zscore",
    "driver_pace_score_vs_grid": "pace_score_grid",
    "driver_pace_score_0_100": "pace_score_100",
    
    # Speed metrics
    "driver_top_speed": "speed_top",
    "driver_corner_speed": "speed_corner",
    "driver_top_speed_rank": "speed_top_rank",
    "driver_corner_speed_rank": "speed_corner_rank",
    "driver_drag_index": "drag_index",
    
    # Additional available features
    "avg_race_pos_3_races": "hist_race_avg_3",
    "avg_race_pos_5_races": "hist_race_avg_5",
    "avg_race_pos_7_races": "hist_race_avg_7",
    "position_gain_from_quali_to_race": "position_gain",
}

# Select and rename columns that exist
available_columns = [col for col in COLUMN_MAPPING.keys() if col in df_raw.columns]
df = df_raw[available_columns + ["race_key", "race_id"]].copy()
df = df.rename(columns=COLUMN_MAPPING)

if "team" in df.columns:
    df["team"] = df.apply(
        lambda row: resolve_team_name(row.get("driver"), row.get("team")),
        axis=1,
    )

print(f"Available columns after mapping: {len(available_columns)}")
print(f"Mapped columns: {[COLUMN_MAPPING[col] for col in available_columns]}")
print(f"Standardized shape: {df.shape}\n")

# ============================================================================
# DATA TYPE CONVERSION
# ============================================================================

# Time columns (convert to seconds)
time_columns = ["fp1_time", "fp2_time", "fp3_time", "q1_time", "q2_time", "q3_time"]
for col in time_columns:
    if col in df.columns:
        df[col] = df[col].apply(time_to_seconds)

# Numeric columns
numeric_columns = [
    "fp1_pos", "fp2_pos", "fp3_pos", "grid_pos",
    "q1_pos", "q2_pos", "q3_pos",
    "track_score", "track_overtakes", "track_sc_pct", "track_vsc_pct", "track_red_pct",
    "pace_avg", "pace_clean_air", "pace_grid_avg", "pace_delta_grid",
    "pace_zscore", "pace_score_grid", "pace_score_100",
    "speed_top", "speed_corner", "speed_top_rank", "speed_corner_rank", "drag_index",
    "hist_race_avg_3", "hist_race_avg_5", "hist_race_avg_7", "position_gain",
]
for col in numeric_columns:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

# Target variable
df["race_finish_pos"] = pd.to_numeric(df["race_finish_pos"], errors="coerce")

# ============================================================================
# AGGREGATE TO DRIVER-RACE LEVEL
# ============================================================================

# Get one row per driver per race
groupby_cols = ["race_id", "season", "race_name", "driver"]
df_driver_race = (
    df.sort_values(["race_id"])
    .groupby(groupby_cols, as_index=False)
    .first()
)

print(f"Driver-race records: {df_driver_race.shape}")

# Check for prediction race
if "race_name" in df_driver_race.columns:
    pred_race_count = df_driver_race["race_name"].eq(PRED_RACE_NAME).sum()
    print(f"'{PRED_RACE_NAME}' appears {pred_race_count} times")
    
    # Show available seasons and races for context
    if pred_race_count == 0:
        print("\nAvailable races in most recent season:")
        latest_season = df_driver_race["season"].max()
        latest_races = df_driver_race[df_driver_race["season"] == latest_season]["race_name"].unique()
        print(f"Season {latest_season}: {list(latest_races)}")

print()

# ============================================================================
# ADD HISTORICAL FEATURES
# ============================================================================

print("Adding historical features...")
df_driver_race = add_driver_history_features(df_driver_race)

# ============================================================================
# TRAIN/PREDICT SPLIT
# ============================================================================

# Split data for prediction race
mask_predict = (
    (df_driver_race["season"] == PRED_SEASON) & 
    (df_driver_race["race_name"] == PRED_RACE_NAME)
)

df_predict = df_driver_race[mask_predict].copy()
df_train = df_driver_race[~mask_predict].copy()

# If the prediction race has no data yet, try two levels of fallback.
if df_predict.shape[0] == 0 and args.from_supabase:
    next_race_id = df_driver_race["race_id"].max() + 1

    # Level 1: Targeted Supabase fetch — qualifying/FP may have been fetched
    # after the main training query ran, so entries exist but weren't captured.
    print(f"No entries for {PRED_SEASON} {PRED_RACE_NAME} in main load — "
          f"attempting targeted Supabase fetch...")
    targeted = load_race_entries_from_supabase(PRED_SEASON, PRED_RACE_NAME)

    if not targeted.empty:
        print(f"Found {len(targeted)} entries via targeted fetch "
              f"(qualifying/FP data present, race not run yet)")
        available_targeted = [c for c in COLUMN_MAPPING.keys() if c in targeted.columns]
        targeted = targeted[available_targeted].copy()
        targeted = targeted.rename(columns=COLUMN_MAPPING)
        for col in time_columns:
            if col in targeted.columns:
                targeted[col] = targeted[col].apply(time_to_seconds)
        for col in numeric_columns + ["race_finish_pos"]:
            if col in targeted.columns:
                targeted[col] = pd.to_numeric(targeted[col], errors="coerce")
        targeted["race_key"] = f"{PRED_SEASON} | {PRED_RACE_NAME}"
        targeted["race_id"] = next_race_id
        targeted = add_driver_history_features_single_race(targeted, df_driver_race)
        df_predict = targeted
        print(f"Using {len(df_predict)} entries with real qualifying/FP data")

    else:
        # Level 2: No entries at all — qualifying hasn't happened yet.
        # Create empty placeholder entries from the season roster.
        print(f"No entries found — creating placeholder entries from roster...")
        placeholder = create_prediction_entries_from_supabase(PRED_SEASON, PRED_RACE_NAME)
        if not placeholder.empty:
            placeholder = placeholder.rename(columns=COLUMN_MAPPING)
            placeholder["race_key"] = f"{PRED_SEASON} | {PRED_RACE_NAME}"
            placeholder["race_id"] = next_race_id
            placeholder = add_driver_history_features_single_race(placeholder, df_driver_race)
            df_predict = placeholder
            print(f"Created {len(df_predict)} placeholder entries (no qualifying data yet)")

# Remove rows without valid finish position from training
df_train = df_train.dropna(subset=["race_finish_pos"]).copy()

print(f"Training records: {df_train.shape[0]}")
print(f"Prediction records: {df_predict.shape[0]}")

if df_predict.shape[0] > 0:
    print(f"\nPrediction race details:")
    cols_to_show = [c for c in ["season", "race_name", "driver", "team"] if c in df_predict.columns]
    print(df_predict[cols_to_show].head(22))
else:
    print(f"\nWARNING: No data found for {PRED_SEASON} {PRED_RACE_NAME}")
    print("\nMost recent races in dataset:")
    recent = df_driver_race.nlargest(20, ["season", "race_id"])[["season", "race_name"]].drop_duplicates()
    print(recent.to_string(index=False))

print()

# ============================================================================
# FEATURE SELECTION
# ============================================================================

# Categorical features
categorical_features = ["driver", "team", "gp_name", "race_name"]

# Numeric features
numeric_features = [
    # Track characteristics
    "track_score", "track_overtakes", "track_sc_pct", "track_vsc_pct", "track_red_pct",
    
    # Practice sessions
    "fp1_pos", "fp1_time", "fp2_pos", "fp2_time", "fp3_pos", "fp3_time",
    
    # Qualifying
    "grid_pos", "q1_time", "q2_time", "q3_time",
    "q1_pos", "q2_pos", "q3_pos",
    
    # Driver performance
    "pace_avg", "pace_clean_air", "pace_grid_avg", "pace_delta_grid",
    "pace_zscore", "pace_score_grid", "pace_score_100",
    
    # Speed metrics
    "speed_top", "speed_corner", "speed_top_rank", "speed_corner_rank", "drag_index",
    
    # Historical features (custom rolling)
    "hist_finish_lag1", "hist_finish_roll3", "hist_finish_roll5",
    "hist_grid_lag1", "hist_grid_roll3", "hist_grid_roll5",
    "hist_q3_roll3", "hist_q3_roll5",
    
    # Historical features (from CSV)
    "hist_race_avg_3", "hist_race_avg_5", "hist_race_avg_7",
    "position_gain",
]

# Use only features that exist in the data
all_features = categorical_features + numeric_features
available_features = [f for f in all_features if f in df_train.columns]

print(f"Using {len(available_features)} features:")
cat_features = [f for f in categorical_features if f in available_features]
num_features = [f for f in numeric_features if f in available_features]
print(f"  Categorical: {cat_features}")
print(f"  Numeric: {len(num_features)} features\n")

# ============================================================================
# PREPARE TRAINING DATA
# ============================================================================

X_train = df_train[available_features].copy()

# Ensure all expected features exist in prediction data (may be NaN for future races)
for feat in available_features:
    if feat not in df_predict.columns:
        df_predict[feat] = np.nan
X_predict = df_predict[available_features].copy()

# Convert categorical columns
for col in categorical_features:
    if col in available_features:
        X_train[col] = X_train[col].astype("category")
        X_predict[col] = X_predict[col].astype("category")

# Create ranking labels (higher is better).
# Use each race's own classified field size instead of assuming 20 drivers,
# so 22-car grids don't produce negative labels for P21/P22.
race_max_finish = df_train.groupby("race_id")["race_finish_pos"].transform("max")
y_train = (race_max_finish + 1 - df_train["race_finish_pos"]).clip(lower=0).astype(int)

# Group sizes for ranking (one group per race)
train_groups = df_train.groupby("race_id").size().values

print(f"Training races: {len(train_groups)}")
print(f"Drivers per race - mean: {train_groups.mean():.1f}, median: {np.median(train_groups):.0f}")
print(f"Races with != 20 drivers: {(train_groups != 20).sum()}\n")

# ============================================================================
# TRAIN MODEL
# ============================================================================

print("Training LightGBM Ranker...")

n_train_rows = len(X_train)
n_train_races = len(train_groups)

if n_train_rows < 100 or n_train_races <= 5:
    print(f"  Small-data mode ({n_train_rows} rows, {n_train_races} races) — reduced complexity")
    model = LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        n_estimators=200,
        learning_rate=0.05,
        num_leaves=15,
        min_child_samples=3,
        subsample=0.9,
        colsample_bytree=0.6,
        reg_alpha=1.0,
        reg_lambda=2.0,
        random_state=42,
        verbose=-1,
    )
else:
    model = LGBMRanker(
        objective="lambdarank",
        metric="ndcg",
        n_estimators=2000,
        learning_rate=0.02,
        num_leaves=63,
        min_child_samples=20,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        verbose=-1,
    )

model.fit(
    X_train,
    y_train,
    group=train_groups,
    categorical_feature=cat_features,
)

print("Training complete!\n")

# ============================================================================
# MAKE PREDICTIONS
# ============================================================================

if df_predict.shape[0] > 0:
    print(f"Predicting results for {PRED_SEASON} {PRED_RACE_NAME}...\n")
    
    prediction_scores = model.predict(X_predict)
    
    # Create results dataframe
    result_cols = ["driver", "team"]
    if "grid_pos" in df_predict.columns:
        result_cols.append("grid_pos")
    results = df_predict[result_cols].copy()
    if "grid_pos" not in results.columns:
        results["grid_pos"] = np.nan
    results["team"] = results.apply(
        lambda row: resolve_team_name(row["driver"], row.get("team")),
        axis=1,
    )
    results["prediction_score"] = prediction_scores
    
    # Rank by prediction score (higher = better predicted finish)
    results = results.sort_values("prediction_score", ascending=False).reset_index(drop=True)
    results["predicted_position"] = np.arange(1, len(results) + 1)
    
    include_grid_pos = (
        "grid_pos" in results.columns and results["grid_pos"].notna().any()
    )

    # Reorder columns for display
    display_cols = ["predicted_position", "driver", "team"]
    if include_grid_pos:
        display_cols.append("grid_pos")
    display_cols.append("prediction_score")
    results = results[display_cols]
    
    print("=" * 85)
    print(f"PREDICTED RACE RESULTS: {PRED_SEASON} {PRED_RACE_NAME}")
    print("=" * 85)
    print(results.to_string(index=False))
    print("=" * 85)
    
    # Feature importance
    print("\nTop 15 Most Important Features:")
    feature_importance = pd.DataFrame({
        "feature": model.feature_name_,
        "importance": model.feature_importances_
    }).sort_values("importance", ascending=False).head(15)
    print(feature_importance.to_string(index=False))
    
    # ============================================================================
    # SAVE MODEL AND PREDICTIONS FOR API SERVICE
    # ============================================================================
    
    # Save predictions to CSV for FastAPI service
    results_with_race_info = results.copy()
    results_with_race_info["season"] = PRED_SEASON
    results_with_race_info["race_name"] = PRED_RACE_NAME
    
    predictions_output = SCRIPT_DIR / "latest_predictions.csv"
    results_with_race_info.to_csv(predictions_output, index=False)
    print(f"\n✓ Predictions saved to {predictions_output}")
    
    if args.from_supabase:
        upsert_predictions_to_supabase(results, PRED_SEASON, PRED_RACE_NAME)
        try:
            from data_pipeline.ai_insights import generate_prediction_insight

            generate_prediction_insight(results, PRED_SEASON, PRED_RACE_NAME)
        except Exception as exc:
            print(f"AI insight skipped after prediction upsert: {exc}")
    
else:
    print("No prediction data available. Please check your season and race name.")
    print("The model has been trained and is ready for predictions once data is available.")

# ============================================================================
# SAVE TRAINED MODEL
# ============================================================================

model_output = SCRIPT_DIR / "f1_ranker_model.pkl"
joblib.dump(model, model_output)
print(f"✓ Model saved to {model_output}")
print(f"\nModel size: {model_output.stat().st_size / 1024:.1f} KB")
print("\n" + "=" * 85)
print("Training and prediction complete!")
print("To start the prediction API service, run:")
print("  python prediction_service.py")
print("=" * 85)

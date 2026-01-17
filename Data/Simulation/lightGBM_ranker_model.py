# pip install lightgbm scikit-learn pandas numpy

import pandas as pd
import numpy as np
import re
from lightgbm import LGBMRanker

# ============================================================================
# CONFIGURATION
# ============================================================================
DATA_PATH = "Car_Tyre_CSV/master_combined_data.csv"
PRED_SEASON = 2025
PRED_RACE_NAME = "Yas Marina Circuit"

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


# ============================================================================
# LOAD AND PREPARE DATA
# ============================================================================

print("Loading data...")
df_raw = pd.read_csv(DATA_PATH, low_memory=False)

print(f"Raw data shape: {df_raw.shape}")
print(f"Columns: {list(df_raw.columns)}\n")

# Create unique race identifier
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

# Remove rows without valid finish position from training
df_train = df_train.dropna(subset=["race_finish_pos"]).copy()

print(f"Training records: {df_train.shape[0]}")
print(f"Prediction records: {df_predict.shape[0]}")

if df_predict.shape[0] > 0:
    print(f"\nPrediction race details:")
    print(df_predict[["season", "race_name", "driver", "team"]].head(10))
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
X_predict = df_predict[available_features].copy()

# Convert categorical columns
for col in categorical_features:
    if col in available_features:
        X_train[col] = X_train[col].astype("category")
        X_predict[col] = X_predict[col].astype("category")

# Create ranking labels (higher is better)
# Convert finish position (1=best) to relevance score (20=best)
y_train = (21 - df_train["race_finish_pos"]).astype(int)

# Group sizes for ranking (one group per race)
train_groups = df_train.groupby("race_id").size().values

print(f"Training races: {len(train_groups)}")
print(f"Drivers per race - mean: {train_groups.mean():.1f}, median: {np.median(train_groups):.0f}")
print(f"Races with != 20 drivers: {(train_groups != 20).sum()}\n")

# ============================================================================
# TRAIN MODEL
# ============================================================================

print("Training LightGBM Ranker...")

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
    results = df_predict[["driver", "team", "grid_pos"]].copy()
    results["prediction_score"] = prediction_scores
    
    # Rank by prediction score (higher = better predicted finish)
    results = results.sort_values("prediction_score", ascending=False).reset_index(drop=True)
    results["predicted_position"] = np.arange(1, len(results) + 1)
    
    # Reorder columns for display
    results = results[[
        "predicted_position", "driver", "team", 
        "grid_pos", "prediction_score"
    ]]
    
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
    
else:
    print("No prediction data available. Please check your season and race name.")
    print("The model has been trained and is ready for predictions once data is available.")
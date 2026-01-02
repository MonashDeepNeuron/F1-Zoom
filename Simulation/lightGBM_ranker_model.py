#pip install lightgbm

import pandas as pd
import numpy as np
import re
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import GroupShuffleSplit

# LOAD THE CSV #
PATH = "Car_Tyre_CSV/master_combined_data.csv"

df = pd.read_csv(PATH)

PRED_SEASON = 2025
PRED_RACE_NAME = "Yas Marina Circuit"

# print(df.head())

# print(df.columns)

# print(df.shape)

# print(df.info())

# created a race_id
race_keys = df[["season", "race_name"]].astype(str).agg(" | ".join, axis=1)
df["_race_key"] = race_keys

df["_race_id"] = pd.factorize(df["_race_key"], sort=False)[0]



pre_race_cols = [
    "season","race_name","gp_name","driver","team",
    "track_score","track_avg_overtakes","track_sc_pct","track_vsc_pct","track_red_pct",
    "fp1_pos","fp1_time","fp2_pos","fp2_time","fp3_pos","fp3_time",
    "quali_grid_pos","q1_time","q2_time","q3_time",
    "race_finish_pos","race_status"
]

driver_race = (
    df.sort_values(["_race_id"])  # ensures consistent order
      .groupby(["_race_id","season","race_name","driver"], as_index=False)[pre_race_cols]
      .first()
)

# Check where "Yas Marina Circuit" appears
for col in ["race_name", "gp_name"]:
    print(col, driver_race[col].isin(["Yas Marina Circuit"]).sum())


# print(driver_race.shape)
# print(driver_race.head())

def time_to_seconds(x):
    """Ensure all time is in float seconds"""
    if pd.isna(x):
        return np.nan
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip()
    if s in ["", "None", "nan"]:
        return np.nan
    
    # Match M:SS(.mmm) or SS(.mmm)
    m = re.match(r"^(?:(\d+):)?(\d+(?:\.\d+)?)$", s)
    if not m:
        return np.nan
    minutes = float(m.group(1)) if m.group(1) else 0.0
    seconds = float(m.group(2))
    return 60.0 * minutes + seconds

time_cols = ["fp1_time","fp2_time","fp3_time","q1_time","q2_time","q3_time"]
for c in time_cols:
    driver_race[c] = driver_race[c].apply(time_to_seconds)

# numeric cols that should be numeric
num_cols = [
    "fp1_pos","fp2_pos","fp3_pos","quali_grid_pos",
    "track_score","track_avg_overtakes","track_sc_pct","track_vsc_pct","track_red_pct",
]
for c in num_cols:
    driver_race[c] = pd.to_numeric(driver_race[c], errors="coerce")

# target
driver_race["race_finish_pos"] = pd.to_numeric(driver_race["race_finish_pos"], errors="coerce")


# Add history features without leakage
driver_race = driver_race.sort_values(["season","_race_id","driver"]).reset_index(drop=True)

def add_driver_rolling_features(df, group_col="driver"):
    g = df.groupby(group_col, sort=False)

    # Lag features (previous race)
    df["finish_pos_lag1"] = g["race_finish_pos"].shift(1)
    df["grid_lag1"] = g["quali_grid_pos"].shift(1)

    # Rolling means (using only prior races -> shift(1) before rolling)
    df["finish_pos_roll3"] = g["race_finish_pos"].shift(1).rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
    df["finish_pos_roll5"] = g["race_finish_pos"].shift(1).rolling(5, min_periods=1).mean().reset_index(level=0, drop=True)

    df["grid_roll3"] = g["quali_grid_pos"].shift(1).rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
    df["grid_roll5"] = g["quali_grid_pos"].shift(1).rolling(5, min_periods=1).mean().reset_index(level=0, drop=True)

    df["q3_roll3"] = g["q3_time"].shift(1).rolling(3, min_periods=1).mean().reset_index(level=0, drop=True)
    df["q3_roll5"] = g["q3_time"].shift(1).rolling(5, min_periods=1).mean().reset_index(level=0, drop=True)

    return df

driver_race = add_driver_rolling_features(driver_race)

# Use LightGBM Ranker 
# each race is a query group
# model learns to rank drivers within each race 
race_group_sizes = driver_race.groupby("_race_id").size()

# Basic sanity check: you want (mostly) 20 drivers per race
print(race_group_sizes.describe())
print("Races with != 20 drivers:", (race_group_sizes != 20).sum())

# choose the prediction race (Abu Dhabi) and split the training / prediction data
# defined at the top of the file
mask_pred = (driver_race["season"] == PRED_SEASON) & (driver_race["race_name"] == PRED_RACE_NAME)
pred_df = driver_race[mask_pred].copy()

train_df = driver_race[~mask_pred].copy()

print("Train rows:", train_df.shape, "Predict rows:", pred_df.shape)
print(pred_df[["season","race_name"]].drop_duplicates())




# Prepare features and handle missing values
from lightgbm import LGBMRanker

# Features we will use (pre-race + rolling form)
feature_cols = [
    # Identifiers (categorical)
    "driver","team","gp_name","race_name",

    # Track characteristics
    "track_score","track_avg_overtakes","track_sc_pct","track_vsc_pct","track_red_pct",

    # Practice
    "fp1_pos","fp1_time","fp2_pos","fp2_time","fp3_pos","fp3_time",

    # Qualifying
    "quali_grid_pos","q1_time","q2_time","q3_time",

    # Form / history
    "finish_pos_lag1","finish_pos_roll3","finish_pos_roll5",
    "grid_lag1","grid_roll3","grid_roll5",
    "q3_roll3","q3_roll5",
]

# Keep only rows with a valid finish position for training
train_df = train_df.dropna(subset=["race_finish_pos"]).copy()

X_train = train_df[feature_cols].copy()
X_pred  = pred_df[feature_cols].copy()

# LightGBM can handle categoricals directly if dtype="category"
cat_cols = ["driver","team","gp_name","race_name"]
for c in cat_cols:
    X_train[c] = X_train[c].astype("category")
    X_pred[c]  = X_pred[c].astype("category")

# Ranking label: higher is better.
# If finish_pos=1 is best, convert to relevance score 21-finish.
y_train = (21 - train_df["race_finish_pos"]).astype(int)

# Group sizes aligned to X_train order
train_groups = train_df.groupby("_race_id").size().values


# Train the Ranker Model
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
)

model.fit(
    X_train, y_train,
    group=train_groups,
    categorical_feature=cat_cols,
)


# Predict Abu Dhabi
pred_scores = model.predict(X_pred)

out = pred_df[["driver","team","quali_grid_pos"]].copy()
out["score"] = pred_scores

# Higher score = predicted better finish
out = out.sort_values("score", ascending=False).reset_index(drop=True)
out["predicted_finish_pos"] = np.arange(1, len(out) + 1)

print(out[["predicted_finish_pos","driver","team","quali_grid_pos","score"]])


# Prediction Data Inventory

This document inventories the data columns and engineered features in this repo that are collected, created, or consumed to support the race prediction model.

Primary sources:
- `Data/Simulation/lightgbm_model.py`
- `data_pipeline/fetchers/session_fetcher.py`
- `data_pipeline/orchestrator.py`
- `backend/sql/supabase_safe_migrate.sql`
- `data_pipeline/car_data/Car_Tyre_CSV/*.csv`

## 1. Current Live LightGBM Inputs

These are the feature names the current model can consume in `Data/Simulation/lightgbm_model.py`.

### Categorical model inputs

- `driver`
- `team`
- `gp_name`
- `race_name`

### Numeric model inputs

- Track features: `track_score`, `track_overtakes`, `track_sc_pct`, `track_vsc_pct`, `track_red_pct`
- Practice features: `fp1_pos`, `fp1_time`, `fp2_pos`, `fp2_time`, `fp3_pos`, `fp3_time`
- Qualifying features: `grid_pos`, `q1_time`, `q2_time`, `q3_time`, `q1_pos`, `q2_pos`, `q3_pos`
- Race pace features: `pace_avg`, `pace_clean_air`, `pace_grid_avg`, `pace_delta_grid`, `pace_zscore`, `pace_score_grid`, `pace_score_100`
- Speed/cornering features: `speed_top`, `speed_corner`, `speed_top_rank`, `speed_corner_rank`, `drag_index`
- In-model historical features: `hist_finish_lag1`, `hist_finish_roll3`, `hist_finish_roll5`, `hist_grid_lag1`, `hist_grid_roll3`, `hist_grid_roll5`, `hist_q3_roll3`, `hist_q3_roll5`
- Stored historical form features: `hist_race_avg_3`, `hist_race_avg_5`, `hist_race_avg_7`, `position_gain`

### Training label and support fields

- Training target: `race_finish_pos`
- Non-feature support fields: `season`, `race_key`, `race_id`

### Important note

- The model code still supports track features from the older CSV workflow, but the current Supabase training loader does not populate `track_score`, `track_overtakes`, `track_sc_pct`, `track_vsc_pct`, or `track_red_pct`.

## 2. Current Supabase Driver-Race Data (`driver_race_entries`)

These are the row-level columns stored for each driver in each race weekend.

### Keys and metadata

- `id`
- `race_id`
- `driver_id`
- `team_id`
- `created_at`

### Practice data

- `fp1_pos`
- `fp1_time_fastest_lap`
- `fp2_pos`
- `fp2_time_fastest_lap`
- `fp3_pos`
- `fp3_time_fastest_lap`

### Qualifying data

- `qualifying_pos`
- `qualifying_final_grid_pos`
- `q1_time_seconds`
- `q1_position`
- `q1_fastest_lap`
- `q2_time_seconds`
- `q2_position`
- `q2_fastest_lap`
- `q3_time_seconds`
- `q3_position`
- `q3_fastest_lap`

### Sprint qualifying data

- `sprint_qualifying_final_grid_pos`
- `sq1_time_seconds`
- `sq1_position`
- `sq1_fastest_lap`
- `sq2_time_seconds`
- `sq2_position`
- `sq2_fastest_lap`
- `sq3_time_seconds`
- `sq3_position`
- `sq3_fastest_lap`

### Race result data

- `race_finish_pos`
- `race_status`
- `fastest_lap`
- `position_gain_from_quali_to_race`
- `sprint_finish_pos`
- `sprint_fastest_lap`

### Engineered driver race metrics

- `driver_avg_pace`
- `driver_clean_air_pace`
- `driver_grid_avg_pace`
- `driver_pace_delta_to_grid`
- `driver_pace_zscore_vs_grid`
- `driver_pace_score_vs_grid`
- `driver_pace_score_0_100`
- `driver_top_speed`
- `driver_corner_speed`
- `driver_top_speed_rank`
- `driver_corner_speed_rank`
- `driver_drag_index`

### Historical form backfills

- `avg_race_pos_3_races`
- `avg_race_pos_5_races`
- `avg_race_pos_7_races`

### Stored but not currently mapped into the live model

- `q1_fastest_lap`
- `q2_fastest_lap`
- `q3_fastest_lap`
- All `sq*` sprint qualifying time/position/fastest-lap columns
- `sprint_qualifying_final_grid_pos`
- `fastest_lap`
- `sprint_finish_pos`
- `sprint_fastest_lap`
- `qualifying_pos`

## 3. Current Supabase Lap-Level Data (`laps`)

These lap rows are collected as support data and can feed future feature engineering.

- `id`
- `driver_race_entry_id`
- `lap_number`
- `lap_time`
- `compound`
- `track_status`
- `stint_index`
- `created_at`

## 4. Model-Created Historical Features

These are created inside `lightgbm_model.py` and are not stored as first-class DB columns.

- `hist_finish_lag1`: previous race finishing position
- `hist_grid_lag1`: previous race grid position
- `hist_finish_roll3`: rolling mean of previous 3 finish positions
- `hist_finish_roll5`: rolling mean of previous 5 finish positions
- `hist_grid_roll3`: rolling mean of previous 3 grid positions
- `hist_grid_roll5`: rolling mean of previous 5 grid positions
- `hist_q3_roll3`: rolling mean of previous 3 Q3 times
- `hist_q3_roll5`: rolling mean of previous 5 Q3 times

## 5. Current Feature Engineering Formulas

- `position_gain_from_quali_to_race = qualifying_pos - race_finish_pos`
- `driver_avg_pace = mean(valid race lap times)`
- `driver_clean_air_pace = mean(valid race lap times where DriverAhead is blank)`
- `driver_grid_avg_pace = mean(driver_avg_pace across all drivers in the race)`
- `driver_pace_delta_to_grid = driver_avg_pace - driver_grid_avg_pace`
- `driver_pace_zscore_vs_grid = driver_pace_delta_to_grid / std(driver_avg_pace within race)`
- `driver_pace_score_vs_grid = -driver_pace_zscore_vs_grid`
- `driver_pace_score_0_100 = 100 * (1 - percentile_rank(driver_avg_pace, ascending=True))`
- `driver_top_speed = max(SpeedST across valid race laps)`
- `driver_corner_speed = mean(min telemetry Speed below 150 km/h on sampled laps)`
- `driver_top_speed_rank = descending rank of driver_top_speed within race`
- `driver_corner_speed_rank = descending rank of driver_corner_speed within race`
- `driver_drag_index = driver_top_speed_rank - driver_corner_speed_rank`
- `avg_race_pos_3_races`, `avg_race_pos_5_races`, `avg_race_pos_7_races` = mean of prior finish positions across the previous 3/5/7 races

## 6. Legacy CSV-Era Data Products

These were part of the older CSV-based feature engineering path and still explain a lot of the feature history in the repo.

### `lap_by_lap_data_track_status.csv`

- `season`
- `race_name`
- `team`
- `driver`
- `lap_number`
- `stint_index`
- `compound`
- `lap_time`
- `track_status`
- `interval_to_car_ahead`
- `in_traffic`

### `lap_by_lap_data.csv`

- `season`
- `race_name`
- `team`
- `driver`
- `lap_number`
- `stint_index`
- `lap_time`
- `track_status`
- `interval_to_car_ahead`
- `in_traffic`

### `stint_analysis.csv`

- `season`
- `race_name`
- `round`
- `circuit_type`
- `team`
- `driver`
- `stint_index`
- `compound`
- `start_lap`
- `end_lap`
- `stint_length_laps`
- `pit_ended_stint`
- `avg_laptime`
- `best_laptime`
- `delta_laptime_first_to_last`
- `laptime_slope_per_lap`
- `avg_throttle_pct`
- `avg_speed`
- `max_speed`
- `min_corner_speed`
- `laps_in_traffic`
- `traffic_lap_pct`
- `avg_interval_to_car_ahead`
- `clean_air_avg_laptime`

### `driver_race_summary.csv`

- `season`
- `driver`
- `race_name`
- `round`
- `circuit_type`
- `team`
- `finishing_position`
- `race_status`
- `avg_race_pace`
- `clean_air_avg_race_pace`
- `grid_avg_race_pace`
- `pace_delta_to_grid`
- `pace_zscore_vs_grid`
- `pace_score_vs_grid`
- `pace_score_0_100`
- `top_speed`
- `cornering_speed`
- `top_speed_rank`
- `corner_speed_rank`
- `drag_index`
- `avg_stint_length`
- `stints_soft`
- `stints_medium`
- `stints_hard`
- `deg_soft_slope`
- `deg_medium_slope`
- `deg_hard_slope`
- `dropoff_soft`
- `dropoff_medium`
- `dropoff_hard`
- `avg_throttle_pct`
- `avg_speed`
- `traffic_lap_pct`
- `avg_interval_to_car_ahead`
- `clean_air_pace_advantage`

### `track_overtaking_data.csv`

- `track_name`
- `score`
- `avg_overtakes`
- `sc_pct`
- `vsc_pct`
- `red_pct`

### `qualifying_to_race_performance.csv`

- `season`
- `race_name`
- `driver`
- `team`
- `fp1_pos`
- `fp1_time_fastest_lap`
- `fp2_pos`
- `fp2_time_fastest_lap`
- `fp3_pos`
- `fp3_time_fastest_lap`
- `Qualifying_Final_Grid_Position`
- `Q1_time_seconds`
- `Q1_position`
- `Q1_fastest_lap`
- `Q2_time_seconds`
- `Q2_position`
- `Q2_fastest_lap`
- `Q3_time_seconds`
- `Q3_position`
- `Q3_fastest_lap`
- `Race_Finishing_Position`
- `fastest_lap`
- `qualifying_pos`
- `race_pos`
- `position_gain_from_quali_to_race`
- `round`
- `avg_race_pos_3_races`
- `avg_race_pos_5_races`
- `avg_race_pos_7_races`

### Sprint-specific legacy columns supported by the qualifying/race script

- `Sprint_Qualifying_Final_Grid_Position`
- `SQ1_time_seconds`
- `SQ1_position`
- `SQ1_fastest_lap`
- `SQ2_time_seconds`
- `SQ2_position`
- `SQ2_fastest_lap`
- `SQ3_time_seconds`
- `SQ3_position`
- `SQ3_fastest_lap`
- `sprint_race_final_position`
- `sprint_race_fastest_lap`

### `master_combined_data.csv`

This is the old merged feature table that unions the lap, stint, driver-race, track, and qualifying/race datasets. Its exact header is:

`season, race_name, team_x, driver, lap_number, stint_index, compound, lap_time, track_status, interval_to_car_ahead, in_traffic, gp_name, stint_start_lap, stint_end_lap, stint_length, stint_pit_ended, stint_avg_laptime, stint_best_laptime, stint_deg_slope, stint_clean_air_avg, race_finish_pos, race_status, driver_avg_pace, driver_clean_air_pace, driver_grid_avg_pace, driver_pace_delta_to_grid, driver_pace_zscore_vs_grid, driver_pace_score_vs_grid, driver_pace_score_0_100, driver_top_speed, driver_corner_speed, driver_top_speed_rank, driver_corner_speed_rank, driver_drag_index, track_score, track_avg_overtakes, track_sc_pct, track_vsc_pct, track_red_pct, team_y, fp1_pos, fp1_time_fastest_lap, fp2_pos, fp2_time_fastest_lap, fp3_pos, fp3_time_fastest_lap, Qualifying_Final_Grid_Position, Q1_time_seconds, Q1_position, Q1_fastest_lap, Q2_time_seconds, Q2_position, Q2_fastest_lap, Q3_time_seconds, Q3_position, Q3_fastest_lap, Race_Finishing_Position, fastest_lap, qualifying_pos, race_pos, position_gain_from_quali_to_race, round, avg_race_pos_3_races, avg_race_pos_5_races, avg_race_pos_7_races`

## 7. Legacy Track-Level Intermediate Metrics

These were created while building `track_overtaking_data.csv`, even though only a subset is persisted in the final track table.

- `has_safety_car`
- `has_vsc`
- `has_red_flag`
- `total_overtakes`
- `total_laps`
- `racing_laps`
- `excluded_laps`
- `avg_field_size`
- `overtakes_per_lap`
- `overtake_density`
- `top_overtaking_laps`

## 8. Experimental or Planned-but-Not-Wired Prediction Data

These exist in the repo, but they are not currently part of the live LightGBM training path.

### Weather prototype (`data_pipeline/weather.py`)

- `city`
- `temperature`
- `humidity`
- `wind_speed`
- `wind_deg`
- `rain_probability`
- `rain_intensity`
- `rain_category`

### Team/pit/reliability experiments

- `num_pit_stops`
- `average_pit_loss`
- `mechanical_dnf_likelihood`
- `season_avg_pitstop_time`
- `car_rank`

### Declared but not actually persisted as part of the live pipeline

- `weighted_performance_score`

## 9. Bottom Line

If you only care about the current production prediction stack, focus on:

- The 46 potential LightGBM input features in Section 1
- The full `driver_race_entries` and `laps` schemas in Sections 2 and 3
- The in-model historical features in Section 4

If you want the complete feature history of the project, Sections 6 through 8 are the rest of it.

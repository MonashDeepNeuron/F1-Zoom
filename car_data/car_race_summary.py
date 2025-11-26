# one row, per team per race, summarising the driver-lvel stint / lap data

# race pace rank
# qualifying pace rank
# top speed rank
# corner speed rank
# drag index (top_speed_rank - corner_speed_rank)
# circuit type (track vs street)
# avg race pace
# avg stint length

columns = [
    "season", "race_name", "round", "circuit_type",
    "team",

    # Pace
    "avg_race_pace",                 
    "clean_air_avg_race_pace",       # using clean_air_avg_laptime from stints
    "avg_quali_pace",                
    "race_vs_quali_delta",           

    # Speed & Cornering
    "top_speed",                     
    "cornering_speed",               
    "top_speed_rank",                
    "corner_speed_rank",
    "drag_index",                    # top_speed_rank - corner_speed_rank

    # Tyre usage
    "avg_stint_length",              
    "stints_soft",                  
    "stints_medium",
    "stints_hard", 

    # Per-compound degradation (averaged for the race)
    "deg_soft_slope",                # mean laptime_slope_per_lap for SOFT
    "deg_medium_slope",
    "deg_hard_slope",

    # Per-compound drop-off (3rd lap vs last lap)
    "dropoff_soft",
    "dropoff_medium",
    "dropoff_hard",

    # Throttle / PU Behaviour
    "avg_throttle_pct",              # weighted across all stints
    "avg_speed",                     # total race avg speed (from stints)

    # Traffic / Clean Air Behaviour
    "traffic_lap_pct",               
    "avg_interval_to_car_ahead",     
    "clean_air_pace_advantage",      # clean_air_avg_pace - avg_race_pace

    # Reliability
    "mechanical_dnf_count",

    # Pit Crew
    "avg_pitstop_time"
]
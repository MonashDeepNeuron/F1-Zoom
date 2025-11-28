# data frame columns

# we would have 1 row for:
    # each driver
    # each race
    # each stint 

# from this we are going to calculate:
    # tyre degredation per compound
    # stint length
    # throttle %
    # max / avg speed
    # min corner speeds
    # drop off (third lap pace - final lap pace) - tyres take time to warm up
    # 
columns = [
    "season", "race_name", "round", "circuit_type",
    "team", "driver", "stint_index", "compound",
    "start_lap", "end_lap", "stint_length_laps",

    # Pace
    "avg_laptime", "best_laptime",
    "delta_laptime_first_to_last", "laptime_slope_per_lap",

    # Telemetry-based
    "avg_throttle_pct", "avg_speed", "max_speed",
    "min_corner_speed",

    # Tyre/usage
    "compound",
    "pit_ended_stint",
    
    # traffic
    "laps_in_trffic",
    "traffic_lap_pct", # boolean
    "avg_interval_to_car_ahead", # seconds
    "clean_air_avg_laptime"
]

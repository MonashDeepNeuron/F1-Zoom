import fastf1.ergast
import fastf1
import pandas as pd

laps_csv = pd.read_csv("Car_Tyre_CSV/lap_by_lap_data_track_status.csv")

import fastf1
import pandas as pd


def compute_pitstops_from_lap_data(
    df: pd.DataFrame,
    traffic_free_only: bool = True
) -> pd.DataFrame:
    # Sort correctly
    df = df.sort_values(["season", "race_name", "driver", "lap_number"])

    # Identify pit laps (stint increases)
    df["prev_stint"] = df.groupby(
        ["season", "race_name", "driver"]
    )["stint_index"].shift(1)

    pit_laps = df[df["stint_index"] > df["prev_stint"]].copy()

    # remove traffic-affected pit laps
    if traffic_free_only:
        pit_laps = pit_laps[~pit_laps["in_traffic"]]

    # Use green-flag, traffic-free laps as baseline
    baseline_laps = df[
        (df["track_status"] == "Green Flag") &
        (~df["in_traffic"])
    ]

    baseline = (
        baseline_laps
        .groupby(["season", "race_name", "driver"])["lap_time"]
        .median()
    )

    pit_laps["baseline_lap_time"] = pit_laps.set_index(
        ["season", "race_name", "driver"]
    ).index.map(baseline)

    pit_laps["pit_loss"] = (
        pit_laps["lap_time"] - pit_laps["baseline_lap_time"]
    )

    pit_summary = (
        pit_laps
        .groupby(["season", "race_name", "driver", "team"], as_index=False)
        .agg(
            num_pit_stops=("pit_loss", "count"),
            average_pit_loss=("pit_loss", "mean")
        )
    )

    return pit_summary





if __name__ == "__main__":
    # print(get_average_pitstop_time_per_driver(2024, "Bahrain Grand Prix"))
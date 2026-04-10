from __future__ import annotations

from pathlib import Path

import fastf1
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).parent
OUT_DIR = BASE_DIR / "TrackCoordinateCSVs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

CACHE_DIR = Path.home() / ".fastf1_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
fastf1.Cache.enable_cache(str(CACHE_DIR))

# Existing files in this project use these 4 columns.
HEADER = "# x_m,y_m,w_tr_right_m,w_tr_left_m"
DEFAULT_RIGHT_WIDTH_M = 7.500
DEFAULT_LEFT_WIDTH_M = 7.500
SAMPLES_PER_TRACK = 900

TARGET_TRACKS = [
    ("Saudi Arabian Grand Prix", "Jeddah.csv"),
    ("Miami Grand Prix", "Miami.csv"),
    ("Monaco Grand Prix", "Monaco.csv"),
    ("Austrian Grand Prix", "Spielberg.csv"),
    ("Hungarian Grand Prix", "Budapest.csv"),
    ("Azerbaijan Grand Prix", "Baku.csv"),
    ("Singapore Grand Prix", "Singapore.csv"),
    ("Las Vegas Grand Prix", "LasVegas.csv"),
    ("Qatar Grand Prix", "Qatar.csv"),
]

# Try newer seasons first, then fallback.
SEASON_CANDIDATES = [2025, 2024, 2023, 2022]


def _resample_xy(x: np.ndarray, y: np.ndarray, target_count: int) -> tuple[np.ndarray, np.ndarray]:
    """Resample XY points by cumulative path length for smoother spacing."""
    dx = np.diff(x)
    dy = np.diff(y)
    segment_lengths = np.sqrt(dx * dx + dy * dy)
    cumulative = np.insert(np.cumsum(segment_lengths), 0, 0.0)

    total_length = float(cumulative[-1])
    if total_length <= 0:
        return x, y

    desired = np.linspace(0.0, total_length, target_count)
    rx = np.interp(desired, cumulative, x)
    ry = np.interp(desired, cumulative, y)
    return rx, ry


def _extract_xy_for_gp(gp_name: str) -> tuple[np.ndarray, np.ndarray, int] | None:
    """Load session telemetry and extract cleaned lap XY for one GP."""
    for season in SEASON_CANDIDATES:
        try:
            schedule = fastf1.get_event_schedule(season)
            if gp_name not in set(schedule["EventName"].astype(str)):
                continue

            session = fastf1.get_session(season, gp_name, "Q")
            session.load(laps=True, telemetry=True, weather=False, messages=False)

            fastest = session.laps.pick_fastest()
            if fastest is None:
                continue

            pos_data = fastest.get_pos_data()
            xy = pd.DataFrame()
            if pos_data is not None and not pos_data.empty and {"X", "Y"}.issubset(pos_data.columns):
                xy = pos_data[["X", "Y"]].dropna()

            # Fallback for sessions where position data is sparse.
            if xy.empty:
                telemetry = fastest.get_telemetry()
                if telemetry is not None and not telemetry.empty and {"X", "Y"}.issubset(telemetry.columns):
                    xy = telemetry[["X", "Y"]].dropna()

            if xy.empty:
                continue

            x = xy["X"].to_numpy(dtype=float)
            y = xy["Y"].to_numpy(dtype=float)

            # Remove repeated adjacent points to avoid interpolation artifacts.
            keep = np.ones(len(x), dtype=bool)
            keep[1:] = (np.diff(x) != 0) | (np.diff(y) != 0)
            x = x[keep]
            y = y[keep]

            if len(x) < 20:
                continue

            rx, ry = _resample_xy(x, y, SAMPLES_PER_TRACK)
            return rx, ry, season
        except Exception:
            continue

    return None


def _write_track_csv(path: Path, x: np.ndarray, y: np.ndarray) -> None:
    right = np.full_like(x, DEFAULT_RIGHT_WIDTH_M, dtype=float)
    left = np.full_like(x, DEFAULT_LEFT_WIDTH_M, dtype=float)

    df = pd.DataFrame(
        {
            "x_m": x,
            "y_m": y,
            "w_tr_right_m": right,
            "w_tr_left_m": left,
        }
    )

    with path.open("w", encoding="utf-8", newline="") as f:
        f.write(HEADER + "\n")
        df.to_csv(f, index=False, header=False, float_format="%.6f")


def main() -> None:
    created = 0
    skipped_existing = 0
    failed = []

    for gp_name, filename in TARGET_TRACKS:
        out_path = OUT_DIR / filename
        if out_path.exists():
            print(f"Skip existing: {filename}")
            skipped_existing += 1
            continue

        extracted = _extract_xy_for_gp(gp_name)
        if extracted is None:
            failed.append(gp_name)
            print(f"Failed: {gp_name}")
            continue

        x, y, season = extracted
        _write_track_csv(out_path, x, y)
        print(f"Created: {filename} from {gp_name} ({season})")
        created += 1

    print("\nSummary")
    print(f"Created: {created}")
    print(f"Skipped existing: {skipped_existing}")
    print(f"Failed: {len(failed)}")
    if failed:
        for gp in failed:
            print(f"  - {gp}")


if __name__ == "__main__":
    main()

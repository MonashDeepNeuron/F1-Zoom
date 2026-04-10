from pathlib import Path

import fastf1
import numpy as np
import pandas as pd

out_dir = Path(__file__).parent / "TrackCoordinateCSVs"
out_path = out_dir / "Melbourne_v12_20260331.csv"
base_path = out_dir / "Melbourne.csv"

fastf1.Cache.enable_cache(str(Path.home() / ".fastf1_cache"))

session = fastf1.get_session(2025, "Australian Grand Prix", "Q")
session.load(laps=True, telemetry=True, weather=False, messages=False)
fastest = session.laps.pick_fastest()
pos = fastest.get_pos_data()[["X", "Y"]].dropna()

x = pos["X"].to_numpy(dtype=float)
y = pos["Y"].to_numpy(dtype=float)
keep = np.ones(len(x), dtype=bool)
keep[1:] = (np.diff(x) != 0) | (np.diff(y) != 0)
x = x[keep]
y = y[keep]

segment = np.sqrt(np.diff(x) ** 2 + np.diff(y) ** 2)
cum = np.insert(np.cumsum(segment), 0, 0.0)
desired = np.linspace(0.0, float(cum[-1]), 900)
rx = np.interp(desired, cum, x)
ry = np.interp(desired, cum, y)

new_df = pd.DataFrame(
    {
        "x_m": rx,
        "y_m": ry,
        "w_tr_right_m": np.full_like(rx, 7.5),
        "w_tr_left_m": np.full_like(rx, 7.5),
    }
)

with out_path.open("w", encoding="utf-8", newline="") as f:
    f.write("# x_m,y_m,w_tr_right_m,w_tr_left_m\n")
    new_df.to_csv(f, index=False, header=False, float_format="%.6f")

old_df = pd.read_csv(
    base_path,
    comment="#",
    header=None,
    names=["x_m", "y_m", "w_tr_right_m", "w_tr_left_m"],
)


def normalize_xy(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    nx = df["x_m"].to_numpy(dtype=float)
    ny = df["y_m"].to_numpy(dtype=float)
    nx = nx - np.mean(nx)
    ny = ny - np.mean(ny)
    scale = max(np.max(np.abs(nx)), np.max(np.abs(ny)), 1e-9)
    return nx / scale, ny / scale


def resample(nx: np.ndarray, ny: np.ndarray, n: int = 500) -> tuple[np.ndarray, np.ndarray]:
    seg = np.sqrt(np.diff(nx) ** 2 + np.diff(ny) ** 2)
    cumd = np.insert(np.cumsum(seg), 0, 0.0)
    target = np.linspace(0.0, float(cumd[-1]), n)
    return np.interp(target, cumd, nx), np.interp(target, cumd, ny)


ox, oy = normalize_xy(old_df)
nx, ny = normalize_xy(new_df)
orx, ory = resample(ox, oy)
nrx, nry = resample(nx, ny)
rmse = float(np.sqrt(np.mean((orx - nrx) ** 2 + (ory - nry) ** 2)))

print(f"Generated: {out_path}")
print(f"Old rows: {len(old_df)} | New rows: {len(new_df)}")
print(
    f"Old width avg (R/L): {old_df['w_tr_right_m'].mean():.3f} / {old_df['w_tr_left_m'].mean():.3f}"
)
print(
    f"New width avg (R/L): {new_df['w_tr_right_m'].mean():.3f} / {new_df['w_tr_left_m'].mean():.3f}"
)
print(f"Old X range: {old_df['x_m'].min():.3f} to {old_df['x_m'].max():.3f}")
print(f"New X range: {new_df['x_m'].min():.3f} to {new_df['x_m'].max():.3f}")
print(f"Old Y range: {old_df['y_m'].min():.3f} to {old_df['y_m'].max():.3f}")
print(f"New Y range: {new_df['y_m'].min():.3f} to {new_df['y_m'].max():.3f}")
print(f"Normalized shape RMSE (lower is closer): {rmse:.4f}")

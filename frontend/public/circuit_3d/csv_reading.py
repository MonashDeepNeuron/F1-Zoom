import csv
import math
import sys
from pathlib import Path
from statistics import median

BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "TrackCoordinateCSVs"
OUTPUT_DIR = BASE_DIR / "TrackCoordinateJS"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PERCENTILE_THRESHOLD = 85
MIN_CORNER_RUN = 4
SMOOTH_WINDOW = 8

"""
For each CSV in TrackCoordinateCSVs/, this script:

  1. Reads x/y coordinate points representing the track layout.
  
  2. Computes curvature at each point using the circumradius of the triangle
     formed by each point and its two neighbours.
     
  3. Smooths the curvature signal with a median filter to reduce noise.
  
  4. Selects corner sections by iterating candidate percentile thresholds
     (90th down to 50th) until the number of detected corners matches the
     official turn count fetched from the database.
     
  5. Ranks corners by total turn angle + peak curvature and trims to the
     target count.
     
  6. Writes a .js file to TrackCoordinateJS/ with an added `is_corner`
     column (1 = corner, 0 = straight).
"""



# ---------------------------------------------------------------------------
# GEOMETRY
# ---------------------------------------------------------------------------

def dist(a, b):
    return math.sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2)


def curvature(p0, p1, p2):
    a, b, c = dist(p0, p1), dist(p1, p2), dist(p0, p2)
    if a * b * c < 1e-12:
        return 0.0
    cross = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])
    area = abs(cross) / 2.0
    return (4.0 * area) / (a * b * c)


def turn_angle(p0, p1, p2):
    v1 = (p1[0] - p0[0], p1[1] - p0[1])
    v2 = (p2[0] - p1[0], p2[1] - p1[1])
    
    len1 = math.sqrt(v1[0] ** 2 + v1[1] ** 2)
    len2 = math.sqrt(v2[0] ** 2 + v2[1] ** 2)
    
    if len1 < 1e-12 or len2 < 1e-12:
        return 0.0
    
    cross = v1[0] * v2[1] - v1[1] * v2[0]
    dot = v1[0] * v2[0] + v1[1] * v2[1]
    
    return abs(math.degrees(math.atan2(cross, dot)))


# ---------------------------------------------------------------------------
# SMOOTHING + PERCENTILE
# ---------------------------------------------------------------------------

def smooth(values, window):
    if window <= 1:
        return list(values)
    half = window // 2
    return [median(values[max(0, i - half):min(len(values), i + half + 1)]) for i in range(len(values))]


def percentile(values, p):
    if not values:
        return 0.0
    s = sorted(values)
    pos = (len(s) - 1) * p / 100.0
    lo, hi = math.floor(pos), math.ceil(pos)
    return s[lo] if lo == hi else s[lo] + (s[hi] - s[lo]) * (pos - lo)


# ---------------------------------------------------------------------------
# CORNER DETECTION
# ---------------------------------------------------------------------------

def find_runs(mask):
    """Return (start, end) index pairs for consecutive True runs in mask."""
    runs, i = [], 0
    while i < len(mask):
        if not mask[i]:
            i += 1
            continue
        start = i
        while i < len(mask) and mask[i]:
            i += 1
        runs.append((start, i))
    return runs


def drop_short_runs(mask, min_len):
    result = list(mask)
    for start, end in find_runs(result):
        if end - start < min_len:
            result[start:end] = [False] * (end - start)
    return result


def mask_from_runs(n, runs):
    mask = [False] * n
    for start, end in runs:
        mask[start:end] = [True] * (end - start)
    return mask


def rank_runs(points, curvatures, runs):
    angles = [0.0] * len(points)
    for i in range(1, len(points) - 1):
        angles[i] = turn_angle(points[i - 1], points[i], points[i + 1])

    ranked = sorted(
        runs,
        key=lambda r: (sum(angles[r[0]:r[1]]), max(curvatures[r[0]:r[1]], default=0.0), r[1] - r[0]),
        reverse=True,
    )
    return ranked


def select_corners(points, curvatures, target_count):
    nonzero = [v for v in curvatures if v > 0.0]
    if not nonzero:
        return [], 0.0, None, 0

    best = {"runs": [], "threshold": 0.0, "pct": None, "count": 0, "found": False}

    for pct in [90, 85, 80, 75, 70, 65, 60, 55, 50]:
        threshold = percentile(nonzero, pct)
        mask = drop_short_runs([v > threshold for v in curvatures], MIN_CORNER_RUN)
        runs = find_runs(mask)
        count = len(runs)

        if target_count and count >= target_count:
            if not best["found"] or count < best["count"]:
                best = {"runs": runs, "threshold": threshold, "pct": pct, "count": count, "found": True}
        elif not best["found"] and count > best["count"]:
            best = {"runs": runs, "threshold": threshold, "pct": pct, "count": count, "found": False}

    ranked = rank_runs(points, curvatures, best["runs"])
    if target_count and target_count > 0:
        ranked = ranked[:target_count]

    return [(r[0], r[1]) for r in ranked], best["threshold"], best["pct"], best["count"]


# ---------------------------------------------------------------------------
# DB LOOKUP
# ---------------------------------------------------------------------------

def get_turn_count(track_name):
    repo_root = str(BASE_DIR.parents[2])
    if repo_root not in sys.path:
        sys.path.append(repo_root)
    from data_pipeline.db.queries import get_circuit_turn_count
    return get_circuit_turn_count(track_name)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

for csv_path in sorted(INPUT_DIR.glob("*.csv")):
    rows = [r for r in csv.reader(csv_path.open(newline="")) if any(c.strip() for c in r)]
    if not rows:
        print(f"Skipping empty file: {csv_path.name}")
        continue

    header, data = rows[0], rows[1:]
    points = [(float(r[0]), float(r[1])) for r in data]
    n = len(points)

    raw_curvature = [0.0] * n
    for i in range(1, n - 1):
        raw_curvature[i] = curvature(points[i - 1], points[i], points[i + 1])

    smoothed = smooth(raw_curvature, SMOOTH_WINDOW)

    target = get_turn_count(csv_path.stem)
    runs, threshold, pct, candidate_count = select_corners(points, smoothed, target)
    is_corner = mask_from_runs(n, runs)

    turn_count = len(runs)
    if target is not None and turn_count != target:
        print(f"Warning: requested {target} turns for {csv_path.stem}, but found {turn_count}")

    lines = ["# " + ",".join(header + ["is_corner"])]
    for i, row in enumerate(data):
        lines.append(",".join(row + ["1" if is_corner[i] else "0"]))

    out_path = OUTPUT_DIR / f"{csv_path.stem}.js"
    out_path.write_text("const trackData = `\n" + "\n".join(lines) + "\n`;", encoding="utf-8")

    print(f"Wrote {out_path.name} (threshold={threshold:.6f}, percentile={pct}, candidates={candidate_count}) with {turn_count} turns")

print("Done.")

import csv
import math
import sys
from pathlib import Path
from statistics import median

BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "TrackCoordinateCSVs"
OUTPUT_DIR = BASE_DIR / "TrackCoordinateJS"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

PERCENTILE_THRESHOLD = 85  # Cast a wide net; ranking + trimming does the real selection
MIN_CORNER_RUN = 4
SMOOTH_WINDOW = 8
DP_EPSILON_FRACTION = 0.001  # Epsilon = this fraction of the track's bounding-box diagonal

"""
For each CSV in TrackCoordinateCSVs/, this script:

  1. Reads x/y coordinate points representing the track layout.

  2. Simplifies the raw point list with the Douglas-Peucker algorithm, removing
     points that deviate less than DP_EPSILON_FRACTION × bounding-box diagonal
     from the chord between their neighbours.  Scaling epsilon to the track's
     own extent makes the algorithm unit-agnostic (degrees, metres, pixels …).
     The original row data is retained for output — only the point indices used
     for geometry are reduced.

  3. Computes curvature at each point using the circumradius of the triangle
     formed by each point and its two neighbours.

  4. Smooths the curvature signal with a median filter to reduce noise.

  5. Finds all candidate corner runs above PERCENTILE_THRESHOLD, then ranks
     them by total turn angle + peak curvature.

  6. Keeps the top N corners, where N is the official turn count from the DB.

  7. Writes a .js file to TrackCoordinateJS/ with an added `is_corner`
     column (1 = corner, 0 = straight).
"""


# ---------------------------------------------------------------------------
# DOUGLAS-PEUCKER SIMPLIFICATION
# ---------------------------------------------------------------------------

def _perpendicular_distance(point, line_start, line_end):
    """Perpendicular distance from `point` to the line through `line_start`→`line_end`."""
    x0, y0 = point
    x1, y1 = line_start
    x2, y2 = line_end

    dx, dy = x2 - x1, y2 - y1
    line_len_sq = dx * dx + dy * dy

    if line_len_sq < 1e-12:
        # Degenerate segment — return point-to-point distance
        return math.sqrt((x0 - x1) ** 2 + (y0 - y1) ** 2)

    # Project point onto the infinite line, clamped to [0, 1] for the segment
    t = ((x0 - x1) * dx + (y0 - y1) * dy) / line_len_sq
    t = max(0.0, min(1.0, t))
    closest_x = x1 + t * dx
    closest_y = y1 + t * dy
    return math.sqrt((x0 - closest_x) ** 2 + (y0 - closest_y) ** 2)


def douglas_peucker(points, epsilon):
    """
    Recursively simplify `points` (list of (x, y)) using the Douglas-Peucker
    algorithm.

    Returns a sorted list of indices into the original `points` list that
    should be retained.  The first and last points are always kept.

    Args:
        points:  List of (x, y) tuples.
        epsilon: Maximum allowed perpendicular deviation.  Points whose
                 deviation from the chord between their enclosing kept points
                 falls below this threshold are discarded.  Larger values
                 produce a coarser simplification; set to 0 to keep all points.

    Returns:
        List[int]: Sorted indices of retained points.
    """
    if len(points) < 3:
        return list(range(len(points)))

    def _rdp(start, end, kept):
        if end - start < 2:
            return

        # Find the point with the greatest perpendicular distance from the
        # chord between points[start] and points[end].
        max_dist, max_idx = 0.0, start + 1
        for i in range(start + 1, end):
            d = _perpendicular_distance(points[i], points[start], points[end])
            if d > max_dist:
                max_dist, max_idx = d, i

        if max_dist > epsilon:
            kept.add(max_idx)
            _rdp(start, max_idx, kept)
            _rdp(max_idx, end, kept)

    kept_indices = {0, len(points) - 1}
    _rdp(0, len(points) - 1, kept_indices)
    return sorted(kept_indices)


def adaptive_epsilon(points, fraction=DP_EPSILON_FRACTION):
    """
    Return an epsilon scaled to the track's bounding-box diagonal.

    Using a fixed fraction of the diagonal means the simplification strength
    is the same regardless of whether coordinates are in degrees, metres, or
    arbitrary pixel units.
    """
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    diagonal = math.sqrt((max(xs) - min(xs)) ** 2 + (max(ys) - min(ys)) ** 2)
    return fraction * diagonal


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

def clamp01(x: float) -> float:
    return 0.0 if x <= 0.0 else (1.0 if x >= 1.0 else x)


def robust_normalise(values, lo_pct=5, hi_pct=95):
    """
    Robustly scale values to [0, 1] using percentiles.

    Compared to `value / max(value)`, this avoids one extreme corner flattening
    the rest of the lap's signal.
    """
    if not values:
        return []
    lo = percentile(values, lo_pct)
    hi = percentile(values, hi_pct)
    if hi - lo < 1e-12:
        return [0.0 for _ in values]
    return [clamp01((v - lo) / (hi - lo)) for v in values]


def local_maxima_indices(values):
    """Return indices i where values[i] is a local maximum (excluding endpoints)."""
    if len(values) < 3:
        return []
    idxs = []
    for i in range(1, len(values) - 1):
        if values[i] > values[i - 1] and values[i] >= values[i + 1]:
            idxs.append(i)
    return idxs


def circular_distance(i, j, n):
    d = abs(i - j)
    return min(d, n - d)


def select_corner_apexes(points, curvatures, target_count):
    """
    Select exactly `target_count` corner apex indices.

    Strategy:
      - Build a per-point 'cornerness' score from robust-normalised turn angle + curvature
      - Generate many candidate local maxima
      - Pick exactly N using non-maximum suppression (NMS) with an adaptive relaxation loop
    """
    n = len(points)
    if not target_count or target_count <= 0 or n < 3:
        return [], {"reason": "no-target-or-too-few-points", "n": n}

    angles = [0.0] * n
    for i in range(1, n - 1):
        angles[i] = turn_angle(points[i - 1], points[i], points[i + 1])

    curv_norm = robust_normalise(list(curvatures))
    ang_norm = robust_normalise(angles)

    w_angle, w_curv = 0.6, 0.4
    score = [w_angle * ang_norm[i] + w_curv * curv_norm[i] for i in range(n)]

    base_min_sep = max(8, int(0.005 * n))
    # Prevent selecting two peaks inside one corner (e.g., hairpin entry + exit),
    # but keep it feasible to place `target_count` apexes around the lap.
    #
    # A good lower bound is based on the average spacing n / target_count; this
    # avoids Montreal-style underfill when n is small after simplification.
    avg_spacing = n / float(target_count)
    min_sep_floor = max(2, int(0.5 * avg_spacing))

    # Relaxation grid: start strict, relax until we can select exactly N.
    # - min score threshold is a quantile over candidate peak scores
    # - min separation shrinks if we're under-producing due to NMS
    quantiles = [85, 80, 75, 70, 65, 60, 55, 50, 40, 30, 20, 10, 0]
    sep_steps = [
        max(min_sep_floor, base_min_sep),
        max(min_sep_floor, max(6, base_min_sep // 2)),
        max(min_sep_floor, max(4, base_min_sep // 3)),
        min_sep_floor,
    ]
    # Keep unique steps in descending order
    sep_steps = sorted(set(sep_steps), reverse=True)

    best_selected = []
    best_diag = {"base_min_sep": base_min_sep, "n": n}

    peak_idxs = local_maxima_indices(score)
    if not peak_idxs:
        # Degenerate fallback: take top-N by score (excluding endpoints)
        candidates = list(range(1, n - 1))
        candidates.sort(key=lambda i: score[i], reverse=True)
        chosen = candidates[:target_count]
        return chosen, {**best_diag, "fallback": "no-local-maxima"}

    peak_scores = [score[i] for i in peak_idxs]

    # Prefer relaxing the threshold first; only relax separation if necessary.
    for q in quantiles:
        thr = percentile(peak_scores, q) if peak_scores else 0.0
        candidates = [i for i in peak_idxs if score[i] >= thr]
        candidates.sort(key=lambda i: score[i], reverse=True)

        for min_sep in sep_steps:
            selected = []
            for idx in candidates:
                if all(circular_distance(idx, s, n) >= min_sep for s in selected):
                    selected.append(idx)
                    if len(selected) == target_count:
                        return selected, {
                            **best_diag,
                            "selected": len(selected),
                            "min_sep": min_sep,
                            "min_sep_floor": min_sep_floor,
                            "peak_quantile": q,
                            "threshold": thr,
                            "candidate_peaks": len(candidates),
                        }

            # Track best attempt for diagnostics / final fallback
            if len(selected) > len(best_selected):
                best_selected = selected
                best_diag = {
                    **best_diag,
                    "selected": len(selected),
                    "min_sep": min_sep,
                    "min_sep_floor": min_sep_floor,
                    "peak_quantile": q,
                    "threshold": thr,
                    "candidate_peaks": len(candidates),
                }

    # Final fallback: enforce exact-N while still respecting a small separation.
    # If peak maxima are insufficient (or too clustered), fall back to any point
    # with high score (excluding endpoints).
    candidates = list(range(1, n - 1))
    candidates.sort(key=lambda i: score[i], reverse=True)
    forced = []
    for idx in candidates:
        if all(circular_distance(idx, s, n) >= min_sep_floor for s in forced):
            forced.append(idx)
            if len(forced) == target_count:
                break

    return forced, {**best_diag, "min_sep_floor": min_sep_floor, "fallback": "forced-top-score-with-sep"}


# ---------------------------------------------------------------------------
# DB LOOKUP
# ---------------------------------------------------------------------------

_TURN_COUNT_CACHE = None


def _parse_sql_tuple_values(tuple_text: str):
    """
    Parse a single SQL VALUES tuple like:
      ('Melbourne', 'Melbourne', ..., 58, 16, 306.124)
    into a list of tokens (strings), preserving quoted strings without quotes.
    """
    s = tuple_text.strip()
    if s.startswith("("):
        s = s[1:]
    if s.endswith(")"):
        s = s[:-1]

    tokens = []
    i = 0
    n = len(s)
    while i < n:
        while i < n and s[i] in " \t,":
            i += 1
        if i >= n:
            break

        if s[i] == "'":
            i += 1
            start = i
            while i < n:
                if s[i] == "'":
                    break
                i += 1
            tokens.append(s[start:i])
            i += 1  # skip closing quote
            continue

        start = i
        while i < n and s[i] not in ",\n":
            i += 1
        tokens.append(s[start:i].strip())

    return tokens


def _load_turn_counts_from_sql():
    """
    Local fallback for corner counts when DB access isn't available.

    Reads `backend/sql/supabase_circuits_and_schedule.sql` and extracts
    `file_slug -> corners` from the `insert into public.circuits ... values` block.
    """
    global _TURN_COUNT_CACHE
    if _TURN_COUNT_CACHE is not None:
        return _TURN_COUNT_CACHE

    sql_path = BASE_DIR.parents[2] / "backend" / "sql" / "supabase_circuits_and_schedule.sql"
    if not sql_path.exists():
        _TURN_COUNT_CACHE = {}
        return _TURN_COUNT_CACHE

    mapping = {}
    in_values = False
    for line in sql_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.lower().startswith("insert into public.circuits"):
            in_values = True
            continue
        if not in_values:
            continue
        if stripped.endswith(";"):
            # last tuple line typically ends with ");"
            in_values = False

        if not stripped.startswith("(") and not stripped.startswith("('"):
            continue
        tuple_line = stripped.rstrip(",;")
        if not (tuple_line.startswith("(") and tuple_line.endswith(")")):
            continue

        tokens = _parse_sql_tuple_values(tuple_line)
        # Expected shape:
        # [code, file_slug, title, subtitle, flag, timezone, weekend_format, length_km, laps, corners, distance_km]
        if len(tokens) >= 10:
            file_slug = tokens[1]
            corners = tokens[9]
            try:
                mapping[file_slug] = int(corners)
            except Exception:
                continue

    _TURN_COUNT_CACHE = mapping
    return _TURN_COUNT_CACHE


def get_turn_count(track_name):
    repo_root = str(BASE_DIR.parents[2])
    if repo_root not in sys.path:
        sys.path.append(repo_root)
    try:
        from data_pipeline.db.queries import get_circuit_turn_count
        db_value = get_circuit_turn_count(track_name)
        if db_value is not None:
            return db_value
    except Exception:
        # Local fallback for offline / unauthenticated environments.
        pass
    return _load_turn_counts_from_sql().get(track_name)


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

for csv_path in sorted(INPUT_DIR.glob("*.csv")):
    rows = [r for r in csv.reader(csv_path.open(newline="")) if any(c.strip() for c in r)]
    if not rows:
        print(f"Skipping empty file: {csv_path.name}")
        continue

    header, data = rows[0], rows[1:]
    all_points = [(float(r[0]), float(r[1])) for r in data]
    n_original = len(all_points)

    # --- Douglas-Peucker simplification -----------------------------------
    # Epsilon is derived from the track's own bounding-box diagonal so the
    # algorithm behaves consistently regardless of coordinate units.
    dp_epsilon = adaptive_epsilon(all_points)
    kept_indices = douglas_peucker(all_points, dp_epsilon)
    points = [all_points[i] for i in kept_indices]
    n = len(points)

    print(
        f"{csv_path.stem}: simplified {n_original} → {n} points "
        f"({100 * (1 - n / n_original):.1f}% removed, epsilon={dp_epsilon:.4f})"
    )

    # --- Curvature on simplified points -----------------------------------
    raw_curvature = [0.0] * n
    for i in range(1, n - 1):
        raw_curvature[i] = curvature(points[i - 1], points[i], points[i + 1])

    smoothed = smooth(raw_curvature, SMOOTH_WINDOW)

    target = get_turn_count(csv_path.stem)
    apex_idxs, diag = select_corner_apexes(points, smoothed, target)
    apex_orig_idxs = [kept_indices[i] for i in apex_idxs]

    is_corner_apex_original = [False] * n_original
    corner_id_original = [0] * n_original

    # Assign corner_id in lap order (by original index).
    apex_orig_sorted = sorted(apex_orig_idxs)
    for corner_id, orig_i in enumerate(apex_orig_sorted, start=1):
        if 0 <= orig_i < n_original:
            is_corner_apex_original[orig_i] = True
            corner_id_original[orig_i] = corner_id

    apex_count = len(apex_orig_sorted)
    if target is not None and apex_count != target:
        print(f"  Warning: requested {target} corners but marked {apex_count} apexes | diag={diag}")

    # Output: keep `is_corner` for backward compatibility (frontend uses it),
    # but redefine it to mean "apex point" (exactly N ones).
    lines = ["# " + ",".join(header + ["is_corner", "is_corner_apex", "corner_id"])]
    for i, row in enumerate(data):
        is_apex = is_corner_apex_original[i]
        cid = corner_id_original[i]
        lines.append(",".join(row + ["1" if is_apex else "0", "1" if is_apex else "0", str(cid)]))

    out_path = OUTPUT_DIR / f"{csv_path.stem}.js"
    out_path.write_text("const trackData = `\n" + "\n".join(lines) + "\n`;", encoding="utf-8")

    print(
        f"  → Wrote {out_path.name} | target={target}, apexes={apex_count} | diag={diag}"
    )

print("Done.")
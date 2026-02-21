import csv
import math
from pathlib import Path
from statistics import median


# ---------------------------------------------------------------------------
# SETUP: where to read CSVs from and where to write JS files to
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "TrackCoordinateCSVs"
OUTPUT_DIR = BASE_DIR / "TrackCoordinateJS"

# Create the output folder if it doesn't exist yet
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)



# Higher = only the sharpest bends count as corners.
# Lower  = gentler bends also count as corners.
PERCENTILE_THRESHOLD = 85

# If a corner is only a couple of points long, it's probably noise.
# This is the minimum number of consecutive corner points needed to keep it.
MIN_CORNER_RUN = 4

# Smoothing window size for curvature values (must be an odd number).
# Bigger = smoother (less noisy), 1 = no smoothing at all.
SMOOTH_WINDOW = 8


# ---------------------------------------------------------------------------
# HELPER FUNCTIONS
# ---------------------------------------------------------------------------

def distance_between(x1, y1, x2, y2):
    """
    Calculate the straight line distance between two points
    """
    dx = x2 - x1
    dy = y2 - y1
    return math.sqrt(dx * dx + dy * dy)


def calculate_curvature(point_before, point_current, point_after):
    """
    Given three consecutive track points, figure out how much the track
    is bending at the middle point.

    Returns a number:
      - 0 means perfectly straight (no bend)
      - bigger number means sharper bend (tighter corner)

    How it works:
      Imagine drawing a triangle with the three points. A tight corner
      makes a "thin" triangle with a big area relative to its side
      lengths. A straight section makes a nearly-flat triangle with
      almost no area. The formula is:

          curvature = (4 * triangle_area) / (side_a * side_b * side_c)

      This comes from fitting a circle through the three points - a
      small circle means a tight turn, a huge circle means almost straight.
    """
    x0, y0 = point_before
    x1, y1 = point_current
    x2, y2 = point_after

    # Measure the three sides of the triangle
    side_a = distance_between(x0, y0, x1, y1)
    side_b = distance_between(x1, y1, x2, y2)
    side_c = distance_between(x0, y0, x2, y2)

    # If any side has zero length the points overlap — no curvature
    product_of_sides = side_a * side_b * side_c
    if product_of_sides < 0.000000000001:
        return 0.0

    # Calculate the area of the triangle using the cross product
    # (This is a standard geometry trick — no need to fully understand it.)
    cross_product = (x1 - x0) * (y2 - y0) - (y1 - y0) * (x2 - x0)
    triangle_area = abs(cross_product) / 2.0

    curvature = (4.0 * triangle_area) / product_of_sides
    return curvature


def get_percentile(values, percentile_number):
    """
    Find a value from a sorted list that sits at a given percentile.

    For example, the 85th percentile means "the value that 85% of the
    data falls below." We use this to set the curvature threshold —
    only the top 15% sharpest bends get flagged as corners.
    """
    if len(values) == 0:
        return 0.0

    sorted_values = sorted(values)

    if len(sorted_values) == 1:
        return sorted_values[0]

    # Figure out which position in the sorted list corresponds to our percentile
    position = (len(sorted_values) - 1) * (percentile_number / 100.0)

    # The position usually falls between two values, so we blend them
    lower_index = math.floor(position)
    upper_index = math.ceil(position)

    if lower_index == upper_index:
        return sorted_values[int(position)]

    # Linear interpolation between the two surrounding values
    lower_value = sorted_values[lower_index]
    upper_value = sorted_values[upper_index]
    fraction = position - lower_index

    blended_value = lower_value * (1 - fraction) + upper_value * fraction
    return blended_value


def smooth_values(values, window_size):
    """
    Smooth out a list of numbers using a "median filter."

    For each value, we look at its neighbors (within the window) and
    replace it with the median (middle value) of that group. This
    removes spiky noise without shifting the overall shape.

    Example with window_size=3:
      values = [0, 0, 10, 0, 0]
      That spike of 10 is probably noise. The median of [0, 10, 0] is 0,
      so the spike gets smoothed away.
    """
    if window_size <= 1:
        # No smoothing requested — return a copy as-is
        return list(values)

    half_window = window_size // 2
    total_points = len(values)
    smoothed = []

    for i in range(total_points):
        # Grab the neighbors around this point
        start = max(0, i - half_window)
        end = min(total_points, i + half_window + 1)
        neighborhood = values[start:end]

        # Replace this value with the median of its neighborhood
        smoothed.append(median(neighborhood))

    return smoothed


def remove_short_corner_sections(is_corner_list, minimum_length):
    """
    Sometimes the algorithm marks just 1 or 2 points as a "corner" in
    the middle of a straight. That's almost certainly noise, not a real
    turn. This function finds those tiny corner sections and removes them.

    Example with minimum_length=4:
      [False, True, True, False, True, True, True, True, True, False]
                ^--- only 2 long,           ^--- 5 long, that's fine
                     gets removed

      Result:
      [False, False, False, False, True, True, True, True, True, False]
    """
    if minimum_length <= 1:
        return list(is_corner_list)

    result = list(is_corner_list)
    total_points = len(result)
    i = 0

    while i < total_points:
        # Skip past any "straight" points
        if not result[i]:
            i = i + 1
            continue

        # We found the start of a corner section — find where it ends
        start_of_corner = i
        while i < total_points and result[i]:
            i = i + 1
        end_of_corner = i

        # How many points long is this corner section?
        corner_length = end_of_corner - start_of_corner

        # If it's too short, it's probably noise — erase it
        if corner_length < minimum_length:
            for j in range(start_of_corner, end_of_corner):
                result[j] = False

    return result


csv_files = sorted(INPUT_DIR.glob("*.csv"))

for csv_path in csv_files:
    output_js_path = OUTPUT_DIR / f"{csv_path.stem}.js"

    with csv_path.open(newline="") as csvfile:
        reader = csv.reader(csvfile)
        all_rows = []
        for row in reader:
            # Skip completely empty rows
            if len(row) == 0:
                continue
            # Skip rows where every cell is blank
            all_blank = True
            for cell in row:
                if cell.strip() != "":
                    all_blank = False
                    break
            if not all_blank:
                all_rows.append(row)

    if len(all_rows) == 0:
        print(f"Skipping empty file: {csv_path.name}")
        continue

    header = all_rows[0]        # first row is column names
    data_rows = all_rows[1:]    # everything else is actual data

    # Pull out the x,y coordinates from each row
    points = []
    for row in data_rows:
        x = float(row[0])
        y = float(row[1])
        points.append((x, y))

    total_points = len(points)

    # Calculate how much the track bends at each point
    # We need three points to measure a bend (before, current, after),
    # so the first and last points get a curvature of 0.
    curvature_values = [0.0] * total_points

    for i in range(1, total_points - 1):
        point_before = points[i - 1]
        point_current = points[i]
        point_after = points[i + 1]
        curvature_values[i] = calculate_curvature(point_before, point_current, point_after)

    # Smooth the curvature to reduce noise
    smoothed_curvature = smooth_values(curvature_values, SMOOTH_WINDOW)

    # Figure out the threshold - how bendy does a point need to be before we call it a "corner"?
    # Collect only the non-zero curvature values (zero = endpoints)
    nonzero_curvatures = []
    for k in smoothed_curvature:
        if k > 0.0:
            nonzero_curvatures.append(k)

    # Use the 85th percentile as the cutoff. This means only the top
    # 15% sharpest bends are considered corners.
    if len(nonzero_curvatures) > 0:
        threshold = get_percentile(nonzero_curvatures, PERCENTILE_THRESHOLD)
    else:
        threshold = 0.0

    # Label each point as corner or straight
    is_corner = []
    for k in smoothed_curvature:
        if k > threshold:
            is_corner.append(True)
        else:
            is_corner.append(False)

    # Clean up - remove tiny corner blips that are just noise
    is_corner = remove_short_corner_sections(is_corner, MIN_CORNER_RUN)

    # Build the output and write a .js file
    new_header = header + ["is_corner"]
    output_lines = []
    output_lines.append("# " + ",".join(new_header))
    turn_counter = 0

    for i in range(len(data_rows)):
        row = data_rows[i]
        if is_corner[i]:
            corner_value = "1"
            if i == 0 or not is_corner[i - 1]:
                turn_counter += 1
        else:
            corner_value = "0"
        row_with_corner = row + [corner_value]
        output_lines.append(",".join(row_with_corner))

    # Wrap it all in a JS variable so the frontend can use it
    track_data_string = "const trackData = `\n" + "\n".join(output_lines) + "\n`;"
    output_js_path.write_text(track_data_string, encoding="utf-8")

    print(f"Wrote {output_js_path.name} (threshold={threshold:.6f}) from {csv_path.name} with {turn_counter} turns")

print("Done processing all tracks.")

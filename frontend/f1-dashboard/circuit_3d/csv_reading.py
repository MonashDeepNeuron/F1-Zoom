import csv
from pathlib import Path

BASE_DIR = Path(__file__).parent
INPUT_DIR = BASE_DIR / "TrackCoordinateCSVs"
OUTPUT_DIR = BASE_DIR / "TrackCoordinateJS"  # change if you want same folder

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

for csv_path in sorted(INPUT_DIR.glob("*.csv")):
    # Output filename matches CSV basename, e.g. Melbourne.csv -> Melbourne.js
    output_js = OUTPUT_DIR / f"{csv_path.stem}.js"

    with csv_path.open(newline="") as csvfile:
        reader = csv.reader(csvfile)
        rows = list(reader)

    if not rows:
        print(f"⚠️ Skipping empty file: {csv_path.name}")
        continue

    header = rows[0]
    data_rows = rows[1:]

    lines = []
    lines.append("# " + ",".join(header))

    for row in data_rows:
        # Skip blank lines
        if not row or all(cell.strip() == "" for cell in row):
            continue
        lines.append(",".join(row))

    track_data_string = "const trackData = `\n" + "\n".join(lines) + "\n`;"

    output_js.write_text(track_data_string, encoding="utf-8")
    print(f"✅ Wrote {output_js.name} from {csv_path.name}")

print("🏁 Done.")

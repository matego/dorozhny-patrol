"""Export final events_dataset.geojson from CSV (only events with coordinates)."""
import csv, json, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

CSV_PATH = "data/events_dataset.csv"
GEOJSON_PATH = "data/events_dataset.geojson"

with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))

features = []
no_coords = 0
for r in rows:
    try:
        lat = float(r["lat"]) if r["lat"] else None
        lon = float(r["lon"]) if r["lon"] else None
    except (ValueError, KeyError):
        lat = lon = None
    if lat and lon:
        props = {k: r[k] for k in r if k not in ("lat", "lon")}
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props
        })
    else:
        no_coords += 1

geojson = {"type": "FeatureCollection", "features": features}
with open(GEOJSON_PATH, "w", encoding="utf-8") as f:
    json.dump(geojson, f, ensure_ascii=False, indent=1)

print(f"GeoJSON: {len(features)} features ({no_coords} events without coords)")
print(f"Total events in CSV: {len(rows)}")

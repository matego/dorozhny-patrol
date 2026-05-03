"""
Merge agent outputs from batch_results/ and append to data/events_dataset.csv.
Records video_ids in data/processed_videos.txt for resumability.

Run after subagents finish writing their JSON outputs.
"""
import json, csv, os, glob, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

CSV_PATH = "data/events_dataset.csv"
PROCESSED_PATH = "data/processed_videos.txt"
BATCH_DIR = "batch_results"
ALL_VIDEOS = "data/all_videos.json"

FIELDS = ["video_id","video_title","video_date","video_url","youtube_link",
          "timecode","address","geocoded_address","event_type","description","lat","lon"]


def timecode_to_seconds(tc):
    if not tc: return 0
    parts = tc.split(":")
    if len(parts) == 3:
        return int(parts[0])*3600 + int(parts[1])*60 + int(parts[2])
    return 0


# ── Merge agent outputs ──────────────────────────────────────────────────────
new_events = []
processed_now = set()
files = sorted(glob.glob(f"{BATCH_DIR}/agent_*_output.json"))
if not files:
    print("No agent output files found. Did subagents finish?")
    sys.exit(1)

for f in files:
    with open(f, encoding="utf-8") as fp:
        d = json.load(fp)
    new_events.extend(d["events"])
    processed_now.update(d["processed_video_ids"])
    print(f"  {os.path.basename(f)}: {len(d['events'])} events, {len(d['processed_video_ids'])} videos")

# ── Load existing CSV ────────────────────────────────────────────────────────
existing_rows = []
existing_keys = set()
if os.path.exists(CSV_PATH):
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            existing_rows.append(r)
            existing_keys.add((r["video_id"], r["timecode"]))

# ── Append new events ────────────────────────────────────────────────────────
added = 0
duplicates = 0
for ev in new_events:
    yt_link = f"{ev['video_url']}&t={timecode_to_seconds(ev['timecode'])}s"
    row = {
        "video_id": ev["video_id"],
        "video_title": ev["video_title"],
        "video_date": ev.get("video_date", ""),
        "video_url": ev["video_url"],
        "youtube_link": yt_link,
        "timecode": ev["timecode"],
        "address": ev.get("address", ""),
        "geocoded_address": "",
        "event_type": ev.get("event_type", ""),
        "description": ev.get("description", ""),
        "lat": "",
        "lon": ""
    }
    key = (row["video_id"], row["timecode"])
    if key in existing_keys:
        duplicates += 1
        continue
    existing_keys.add(key)
    existing_rows.append(row)
    added += 1

# ── Write CSV ────────────────────────────────────────────────────────────────
os.makedirs("data", exist_ok=True)
with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(existing_rows)

# ── Update processed list ────────────────────────────────────────────────────
processed = set()
if os.path.exists(PROCESSED_PATH):
    with open(PROCESSED_PATH, encoding="utf-8") as f:
        processed = {l.strip() for l in f if l.strip()}
processed.update(processed_now)
with open(PROCESSED_PATH, "w", encoding="utf-8") as f:
    for vid in sorted(processed):
        f.write(vid + "\n")

# ── Cleanup ──────────────────────────────────────────────────────────────────
for p in glob.glob(f"{BATCH_DIR}/agent_*_output.json") + glob.glob(f"{BATCH_DIR}/agent_*_input.txt"):
    os.remove(p)

# ── Stats ────────────────────────────────────────────────────────────────────
total_videos = 0
if os.path.exists(ALL_VIDEOS):
    with open(ALL_VIDEOS, encoding="utf-8") as f:
        total_videos = len(json.load(f))

print()
print(f"Added {added} events ({duplicates} duplicates skipped)")
print(f"Total events in CSV: {len(existing_rows)}")
print(f"Total processed videos: {len(processed)} / {total_videos}")
print(f"Remaining: {total_videos - len(processed)}")

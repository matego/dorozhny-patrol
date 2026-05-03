"""
Coordinator for parallel event extraction from transcripts via Claude subagents.

Workflow:
  1. Run this script with N workers — splits remaining videos into N input files
  2. Open Claude Code (or any Claude API client) and spawn N subagents in parallel,
     each with the prompt from `docs/AGENT_PROMPT.md` and the input file path
  3. Each agent writes JSON to batch_results/agent_<i>_output.json
  4. Run `scripts/_apply_extracted_events.py` — merges JSONs into the dataset

Reproducibility: this script is idempotent. Re-run after each round to get a
new batch of unprocessed videos.

Usage:
    python scripts/3_extract_events.py [num_agents] [videos_per_agent]
    # Defaults: 6 agents, 15 videos each = 90 per round
"""
import os, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

NUM_AGENTS = int(sys.argv[1]) if len(sys.argv) > 1 else 6
VIDEOS_PER_AGENT = int(sys.argv[2]) if len(sys.argv) > 2 else 15

VIDEOS_JSON = "data/all_videos.json"
PROCESSED_PATH = "data/processed_videos.txt"
TRANSCRIPTS_DIR = "transcripts"
BATCH_DIR = "batch_results"

os.makedirs(BATCH_DIR, exist_ok=True)

with open(VIDEOS_JSON, encoding="utf-8") as f:
    videos = json.load(f)

processed = set()
if os.path.exists(PROCESSED_PATH):
    with open(PROCESSED_PATH, encoding="utf-8") as f:
        processed = {l.strip() for l in f if l.strip()}

todo = [
    v["video_id"]
    for v in videos
    if v["video_id"] not in processed
    and os.path.exists(f"{TRANSCRIPTS_DIR}/{v['video_id']}.txt")
]

if not todo:
    print(f"All {len(videos)} videos processed (or no transcripts available).")
    sys.exit(0)

# Clean any leftover input/output from a previous round
import glob
for p in glob.glob(f"{BATCH_DIR}/agent_*.txt") + glob.glob(f"{BATCH_DIR}/agent_*.json"):
    os.remove(p)

# Split into chunks
total = min(NUM_AGENTS * VIDEOS_PER_AGENT, len(todo))
chunk_videos = todo[:total]
chunk_size = len(chunk_videos) // NUM_AGENTS or 1

for i in range(NUM_AGENTS):
    start = i * chunk_size
    end = (i + 1) * chunk_size if i < NUM_AGENTS - 1 else len(chunk_videos)
    chunk = chunk_videos[start:end]
    if not chunk:
        continue
    with open(f"{BATCH_DIR}/agent_{i+1}_input.txt", "w", encoding="utf-8") as f:
        for vid in chunk:
            f.write(vid + "\n")
    print(f"  agent_{i+1}_input.txt: {len(chunk)} videos")

print()
print(f"Round prepared: {total} videos across {NUM_AGENTS} agents")
print(f"Remaining after this round: {len(todo) - total}")
print()
print("Next step: spawn subagents with the prompt template from docs/AGENT_PROMPT.md")
print("Then run: python scripts/_apply_extracted_events.py")

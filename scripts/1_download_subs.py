"""
Download Russian auto-subtitles for all videos in the playlist.
Resumable: skips videos that already have a .vtt file.
"""
import subprocess, json, os, time, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Run from project root: python scripts/1_download_subs.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

PLAYLIST_URL = os.environ.get(
    "DP_PLAYLIST",
    "https://www.youtube.com/playlist?list=PLM3KjKTZVo8MFN0_mADwhrOeE-enbsxWs",
)
SUBS_DIR = "subs"
COOKIES = "cookies.txt"  # exported from browser via "Get cookies.txt LOCALLY"
NODE_PATH = os.environ.get("DP_NODE_PATH", "C:/Program Files/nodejs/node.exe")
VIDEOS_JSON = "data/all_videos.json"
BATCH_SIZE = 5
DELAY_BETWEEN_BATCHES = 5  # seconds

os.makedirs(SUBS_DIR, exist_ok=True)
os.makedirs("data", exist_ok=True)

# ── Step 1: Get full video list (once, cache to file) ─────────────────────────
if os.path.exists(VIDEOS_JSON):
    with open(VIDEOS_JSON, encoding="utf-8") as f:
        videos = json.load(f)
    print(f"Loaded {len(videos)} videos from {VIDEOS_JSON}")
else:
    print("Fetching full playlist... (this may take a minute)")
    result = subprocess.run(
        ["yt-dlp", "--flat-playlist", "--dump-json", PLAYLIST_URL],
        capture_output=True, timeout=300
    )
    videos = []
    for line in result.stdout.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            data = json.loads(line)
            videos.append({
                "video_id": data.get("id", ""),
                "title": data.get("title", ""),
                "upload_date": data.get("upload_date", ""),
                "duration_sec": data.get("duration", ""),
                "url": f"https://www.youtube.com/watch?v={data.get('id','')}"
            })
        except json.JSONDecodeError:
            continue
    with open(VIDEOS_JSON, "w", encoding="utf-8") as f:
        json.dump(videos, f, ensure_ascii=False, indent=2)
    print(f"Fetched {len(videos)} videos, saved to {VIDEOS_JSON}")

# ── Step 2: Filter out already-downloaded ─────────────────────────────────────
todo = []
already = 0
for v in videos:
    vtt_path = os.path.join(SUBS_DIR, f"{v['video_id']}.ru.vtt")
    if os.path.exists(vtt_path) and os.path.getsize(vtt_path) > 100:
        already += 1
    else:
        todo.append(v)

print(f"Already downloaded: {already} | Remaining: {len(todo)}")

if not todo:
    print("All done!")
    sys.exit(0)

# ── Step 3: Download in batches ───────────────────────────────────────────────
log_path = "data/download_log.txt"
total = len(todo)
done = 0
errors = []

def download_batch(batch):
    urls = [v["url"] for v in batch]
    cmd = [
        "yt-dlp",
        "--js-runtimes", f"node:{NODE_PATH}",
        "--remote-components", "ejs:github",
        "--cookies", COOKIES,
        "--write-auto-sub",
        "--sub-lang", "ru",
        "--sub-format", "vtt",
        "--skip-download",
        "--no-warnings",
        "--sleep-requests", "2",
        "--sleep-interval", "1",
        "-o", f"{SUBS_DIR}/%(id)s",
    ] + urls
    result = subprocess.run(cmd, capture_output=True, timeout=300)
    output = result.stdout.decode("utf-8", errors="replace") + result.stderr.decode("utf-8", errors="replace")
    return output, result.returncode

with open(log_path, "a", encoding="utf-8") as log:
    log.write(f"\n=== Download started, {len(todo)} videos remaining ===\n")

    for i in range(0, len(todo), BATCH_SIZE):
        batch = todo[i:i + BATCH_SIZE]
        ids = [v["video_id"] for v in batch]
        print(f"[{done}/{total}] Batch {i//BATCH_SIZE + 1}: {', '.join(ids[:3])}{'...' if len(ids)>3 else ''}", end="", flush=True)

        try:
            output, returncode = download_batch(batch)
            # Detect expired cookies — wait for user to refresh, then continue
            if "Sign in to confirm your age" in output or "Sign in to confirm" in output:
                import time as _time
                cookies_mtime = os.path.getmtime(COOKIES)
                print(f"\n>>> COOKIES EXPIRED after {done + already} videos downloaded.", flush=True)
                print(f">>> Re-export cookies.txt and save it to: {os.path.abspath(COOKIES)}", flush=True)
                print(f">>> Waiting for updated cookies.txt...", flush=True)
                log.write(f"COOKIES EXPIRED at batch {i//BATCH_SIZE+1}, waiting for refresh...\n")
                # Wait until the file is updated
                while os.path.getmtime(COOKIES) == cookies_mtime:
                    _time.sleep(3)
                print(f">>> cookies.txt updated — resuming download!", flush=True)
                log.write("Cookies refreshed, resuming.\n")
            # Count successes
            succeeded = sum(1 for v in batch
                            if os.path.exists(os.path.join(SUBS_DIR, f"{v['video_id']}.ru.vtt"))
                            and os.path.getsize(os.path.join(SUBS_DIR, f"{v['video_id']}.ru.vtt")) > 100)
            failed_batch = [v["video_id"] for v in batch
                            if not os.path.exists(os.path.join(SUBS_DIR, f"{v['video_id']}.ru.vtt"))
                            or os.path.getsize(os.path.join(SUBS_DIR, f"{v['video_id']}.ru.vtt")) <= 100]
            done += succeeded
            errors.extend(failed_batch)
            print(f" -> {succeeded}/{len(batch)} OK" + (f" | failed: {failed_batch}" if failed_batch else ""))
            log.write(f"Batch {i//BATCH_SIZE+1}: {succeeded}/{len(batch)} OK | failed: {failed_batch}\n")
        except subprocess.TimeoutExpired:
            print(f" -> TIMEOUT")
            log.write(f"Batch {i//BATCH_SIZE+1}: TIMEOUT\n")
        except Exception as e:
            print(f" -> ERROR: {e}")
            log.write(f"Batch {i//BATCH_SIZE+1}: ERROR: {e}\n")

        time.sleep(DELAY_BETWEEN_BATCHES)

    # Final count
    actual_done = sum(
        1 for v in videos
        if os.path.exists(os.path.join(SUBS_DIR, f"{v['video_id']}.ru.vtt"))
        and os.path.getsize(os.path.join(SUBS_DIR, f"{v['video_id']}.ru.vtt")) > 100
    )
    print(f"\nDone. Total with subtitles: {actual_done}/{len(videos)}")
    print(f"Failed video IDs saved to: {log_path}")
    log.write(f"\nFinal: {actual_done}/{len(videos)} subtitles downloaded\n")
    log.write(f"Failed IDs: {errors}\n")

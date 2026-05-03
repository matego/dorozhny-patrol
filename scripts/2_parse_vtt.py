"""Parse all VTT files into clean text. Removes YouTube's overlapping captions."""
import re, os, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# Run from project root: python scripts/2_parse_vtt.py
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

CLEAN_DIR = "transcripts"
SUBS_DIR = "subs"
VIDEOS_JSON = "data/all_videos.json"
os.makedirs(CLEAN_DIR, exist_ok=True)


def parse_vtt_clean(path):
    with open(path, encoding="utf-8") as f:
        content = f.read()
    content = re.sub(r"<[^>]+>", "", content)
    blocks = re.split(r"\n\n+", content.strip())
    entries = []
    for block in blocks:
        lines = [l.strip() for l in block.splitlines() if l.strip()]
        ts_line = None
        text_lines = []
        for line in lines:
            if re.match(r"\d{2}:\d{2}:\d{2}\.\d+ --> ", line):
                ts_line = line
            elif line not in ("WEBVTT", "Kind: captions", "Language: ru") and not line.startswith("NOTE"):
                text_lines.append(line)
        if not ts_line: continue
        m = re.match(r"(\d{2}):(\d{2}):(\d{2})", ts_line)
        if not m: continue
        h, mn, s = int(m.group(1)), int(m.group(2)), int(m.group(3))
        start_sec = h*3600 + mn*60 + s
        end_m = re.search(r"--> (\d{2}):(\d{2}):(\d{2})", ts_line)
        if end_m:
            eh, em, es = int(end_m.group(1)), int(end_m.group(2)), int(end_m.group(3))
            if (eh*3600 + em*60 + es) - start_sec < 1: continue
        text = " ".join(text_lines).strip()
        if not text: continue
        entries.append((start_sec, text))
    return entries


def remove_overlap(prev_text, new_text):
    """If end of prev_text overlaps with start of new_text, return new_text minus the overlap."""
    if not prev_text:
        return new_text
    # Try overlaps from longest to shortest
    max_check = min(len(prev_text), len(new_text), 500)
    for length in range(max_check, 0, -1):
        if prev_text.endswith(new_text[:length]):
            return new_text[length:].lstrip()
    return new_text


def smart_join(entries):
    """Join VTT entries removing word-level overlap between consecutive ones."""
    if not entries:
        return []
    output = []  # list of (start_sec, text)
    accumulated_text = ""
    last_start = None

    for start, text in entries:
        # Remove overlap with previously accumulated text (last ~200 chars matter)
        tail = accumulated_text[-300:] if accumulated_text else ""
        new_part = remove_overlap(tail, text)
        if not new_part:
            continue
        if last_start is None:
            last_start = start
        # Time-based chunking: every ~10s start a new line
        if accumulated_text and (start - last_start >= 10):
            output.append((last_start, accumulated_text.strip()))
            accumulated_text = new_part
            last_start = start
        else:
            accumulated_text = (accumulated_text + " " + new_part).strip() if accumulated_text else new_part

    if accumulated_text.strip():
        output.append((last_start or 0, accumulated_text.strip()))

    return output


with open(VIDEOS_JSON, encoding="utf-8") as f:
    videos = json.load(f)

processed = 0
skipped = 0
for v in videos:
    vid = v["video_id"]
    src = f"{SUBS_DIR}/{vid}.ru.vtt"
    dst = f"{CLEAN_DIR}/{vid}.txt"
    if not os.path.exists(src) or os.path.getsize(src) < 100:
        skipped += 1
        continue
    try:
        entries = parse_vtt_clean(src)
        chunks = smart_join(entries)

        with open(dst, "w", encoding="utf-8") as f:
            f.write(f"# {v['title']}\n")
            f.write(f"# Date: {v.get('upload_date','?')} | Duration: {v.get('duration_sec','?')}s\n")
            f.write(f"# URL: {v['url']}\n\n")
            for t, txt in chunks:
                tc = f"{t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d}"
                f.write(f"[{tc}] {txt}\n")
        processed += 1
    except Exception as e:
        print(f"ERROR {vid}: {e}")
        skipped += 1

print(f"Done. Processed: {processed}, Skipped: {skipped}")

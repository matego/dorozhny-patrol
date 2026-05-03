"""
Geocode all unique addresses with caching via OpenStreetMap Nominatim.
Rate-limited to 1 req/sec per Nominatim's terms. Resumable via cache.
"""
import csv, json, time, urllib.request, urllib.parse, os, re, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

CSV_PATH = "data/events_dataset.csv"
CACHE = "data/geocode_cache.json"
USER_AGENT = "DorozhnyPatrolDataset/1.0 (https://github.com/your/repo)"

def load_cache():
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f: return json.load(f)
    return {}

def save_cache(c):
    with open(CACHE, "w", encoding="utf-8") as f: json.dump(c, f, ensure_ascii=False, indent=2)

def normalize_addr(addr):
    """Drop floor/apt/specific building details that hurt geocoding."""
    a = addr
    a = re.sub(r",\s*(?:квартира|кв\.?|этаж)\s*\S+", "", a, flags=re.I)
    a = re.sub(r",\s*корп(?:ус)?\.?\s*\S+", "", a, flags=re.I)
    a = re.sub(r",\s*стр(?:оение)?\.?\s*\S+", "", a, flags=re.I)
    return a.strip()

def geocode(addr):
    params = urllib.parse.urlencode({
        "q": addr, "format": "json", "limit": 1,
        "countrycodes": "ru", "accept-language": "ru"
    })
    url = f"https://nominatim.openstreetmap.org/search?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        if data:
            return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name","")
    except Exception as e:
        pass
    return None, None, ""


with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))
fields = list(rows[0].keys())

# Collect unique addresses
unique_addrs = set()
for r in rows:
    if r["address"]: unique_addrs.add(r["address"])
print(f"Total events: {len(rows)}, unique addresses: {len(unique_addrs)}")

cache = load_cache()
todo = [a for a in unique_addrs if a not in cache]
print(f"Cached: {len(cache)}, to geocode: {len(todo)}")

# Geocode
for i, addr in enumerate(todo):
    norm = normalize_addr(addr)
    lat, lon, display = geocode(norm)
    if not lat:  # try again with simpler form
        m = re.match(r"^([^,]+,\s*\d+)", norm)
        if m:
            lat, lon, display = geocode(m.group(1) + ", Москва")
            if lat: time.sleep(1.1)
    cache[addr] = {"lat": lat, "lon": lon, "display": display, "query": norm}
    if (i+1) % 50 == 0:
        save_cache(cache)
        success = sum(1 for v in cache.values() if v.get("lat"))
        print(f"  {i+1}/{len(todo)} | total cached: {len(cache)}, geocoded: {success}")
    time.sleep(1.1)

save_cache(cache)

# Apply to rows
updated = 0
for r in rows:
    if r["address"] and r["address"] in cache:
        c = cache[r["address"]]
        if c.get("lat"):
            r["lat"] = c["lat"]
            r["lon"] = c["lon"]
            r["geocoded_address"] = c["display"]
            updated += 1

with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

success = sum(1 for v in cache.values() if v.get("lat"))
print(f"\nDone. Geocoded {success}/{len(cache)} unique addresses ({100*success//len(cache)}%)")
print(f"Events with coords: {updated}/{len(rows)}")

"""Retry failed geocoding with smarter query simplification."""
import json, time, urllib.request, urllib.parse, re, csv, os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT_ROOT)

CSV_PATH = "data/events_dataset.csv"
CACHE = "data/geocode_cache.json"
USER_AGENT = "DorozhnyPatrolDataset/1.0"


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
            return float(data[0]["lat"]), float(data[0]["lon"]), data[0].get("display_name", "")
    except Exception:
        pass
    return None, None, ""


def variants(addr):
    """Generate query variants from oldest-most-specific to fallback."""
    out = []
    a = addr

    # Strip floor/apt/building
    a = re.sub(r",\s*(?:квартира|кв\.?|этаж)\s*\S+", "", a, flags=re.I)
    a = re.sub(r",\s*корп(?:ус)?\.?\s*\S+", "", a, flags=re.I)
    a = re.sub(r",\s*стр(?:оение)?\.?\s*\S+", "", a, flags=re.I)
    out.append(a.strip())

    # Strip POI in middle: "ул X, гостиница Y, Москва" → "ул X, Москва"
    poi = r",\s*(?:гостиница|стадион|салон\s+красоты|клуб|ТЦ|торговый\s+центр|магазин|кинотеатр|школа|больница|отделение\s+милиции|МВД)[^,]*"
    a2 = re.sub(poi, "", a, flags=re.I)
    if a2 != a:
        out.append(a2.strip())

    # "дом N" or "д. N" → "N"
    a3 = re.sub(r",\s*дом\s+(\d+)", r", \1", a, flags=re.I)
    a3 = re.sub(r",\s*д\.?\s+(\d+)", r", \1", a3, flags=re.I)
    if a3 != a:
        out.append(a3.strip())
        # Also try without "Москва" prefix
        a4 = re.sub(r",\s*дом\s+(\d+)", r", \1", a, flags=re.I)
        # Combine: simpler street + дом
        m = re.match(r"^([^,]+),\s*дом\s+(\d+)", a, flags=re.I)
        if m:
            out.append(f"{m.group(1).strip()}, {m.group(2)}, Москва")

    # If has "ул." prefix variation
    a5 = re.sub(r"\bул\.\s*", "улица ", a, flags=re.I)
    if a5 != a:
        out.append(a5.strip())

    # Strip everything after street name → "улица X, Москва"
    m = re.match(r"^((?:улица|проспект|шоссе|переулок|бульвар|набережная|проезд|аллея|тупик|площадь)\s+[^,]+|[^,]+\s+(?:улица|проспект|шоссе|переулок|бульвар|набережная|проезд|аллея|тупик|площадь))", a, flags=re.I)
    if m:
        candidate = f"{m.group(1).strip()}, Москва"
        if candidate not in out:
            out.append(candidate)

    # Just the street name without "Москва"
    m = re.match(r"^([^,]+)", a)
    if m:
        candidate = m.group(1).strip()
        if candidate and candidate not in out and "Москва" not in candidate:
            out.append(f"{candidate}, Москва")

    # Dedupe preserving order
    seen = set(); result = []
    for v in out:
        if v and v not in seen:
            seen.add(v); result.append(v)
    return result


with open(CACHE, encoding="utf-8") as f:
    cache = json.load(f)

failed = [a for a, v in cache.items() if not v.get("lat")]
print(f"Retrying {len(failed)} failed addresses with variants...")

new_hits = 0
for i, addr in enumerate(failed):
    for v in variants(addr):
        lat, lon, display = geocode(v)
        time.sleep(1.1)
        if lat:
            cache[addr] = {"lat": lat, "lon": lon, "display": display, "query": v}
            new_hits += 1
            break
    if (i+1) % 50 == 0:
        with open(CACHE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
        print(f"  {i+1}/{len(failed)} | new hits: {new_hits}")

with open(CACHE, "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False, indent=2)

# Apply to CSV
with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))
fields = list(rows[0].keys())

updated = 0
for r in rows:
    if r["address"] and r["address"] in cache:
        c = cache[r["address"]]
        if c.get("lat"):
            r["lat"] = c["lat"]
            r["lon"] = c["lon"]
            r["geocoded_address"] = c.get("display", "")
            updated += 1

with open(CSV_PATH, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

success = sum(1 for v in cache.values() if v.get("lat"))
print(f"\nFinal: {success}/{len(cache)} unique addresses geocoded ({100*success//len(cache)}%)")
print(f"Events with coords: {updated}/{len(rows)} ({100*updated//len(rows)}%)")

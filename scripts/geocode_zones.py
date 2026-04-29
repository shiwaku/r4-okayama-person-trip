"""
マスターデータのゾーンコードに座標を付加するスクリプト

入力:
  data/csv/code_ゾーンコード.csv
  data/csv/01_master_weekday.csv
  data/csv/02_master_holiday.csv

出力:
  data/zone_coords.csv
  data/zone_coords.geojson
"""
import json
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
CSV_DIR = DATA_DIR / "csv"
CACHE_FILE = DATA_DIR / "geocode_cache.json"
OUTPUT_FILE = DATA_DIR / "zone_coords.csv"

# ── Step 1: ゾーンコード表から住所名ルックアップを構築 ──────────────────
print("Step 1: ゾーンコード表を読み込み中...")
zone_df = pd.read_csv(CSV_DIR / "code_ゾーンコード.csv", encoding="utf-8-sig", dtype=str)

# (city_code, town_code) → [(pref_name, city_name, town_name, chome), ...]
COL_PREF      = "都道府県名"
COL_CITY      = "市区町村名"
COL_TOWN      = "大字町丁目名"
COL_CITY_CODE = "都道府県+\n市区町村"
COL_TOWN_CODE = "大字・町"
COL_CHOME     = "丁目"

zone_names = defaultdict(list)
for _, r in zone_df.iterrows():
    pref = r[COL_PREF]
    city = r[COL_CITY]
    town = r[COL_TOWN]
    f    = r[COL_CITY_CODE]
    g    = r[COL_TOWN_CODE]
    h    = r[COL_CHOME]

    if pd.isna(pref) or pd.isna(city) or pd.isna(town) or pd.isna(f) or pd.isna(g):
        continue
    try:
        city_code = str(int(float(f)))
        town_code = str(int(float(g)))
    except (ValueError, TypeError):
        continue
    chome = str(int(float(h))) if pd.notna(h) else "0"
    zone_names[(city_code, town_code)].append((pref, city, town, chome))

print(f"  ゾーン種類数（コード表）: {len(zone_names)}")


def pick_address(entries):
    for pref, city, town, chome in entries:
        if chome == "0":
            return pref, city, town
    return entries[0][0], entries[0][1], entries[0][2]

zone_address = {k: pick_address(v) for k, v in zone_names.items()}

# ── Step 2: マスターデータで使われているゾーンコードを収集 ────────────────
print("Step 2: マスターデータのゾーンコードを収集中...")
all_codes = set()
for fname in ("01_master_weekday.csv", "02_master_holiday.csv"):
    df = pd.read_csv(CSV_DIR / fname, encoding="utf-8-sig", dtype=str,
                     usecols=["出発地_市町村", "出発地_町", "目的地_市町村", "目的地_町"])
    for col_city, col_town in [("出発地_市町村", "出発地_町"), ("目的地_市町村", "目的地_町")]:
        pairs = df[[col_city, col_town]].dropna()
        pairs = pairs[~pairs[col_town].isin(["*", "nan", ""])]
        for _, row in pairs.iterrows():
            try:
                all_codes.add((str(int(float(row[col_city]))), str(int(float(row[col_town])))))
            except (ValueError, TypeError):
                pass

print(f"  ユニークゾーン数: {len(all_codes)}")

# ── Step 3: ジオコーディング（キャッシュ付き） ────────────────────────
print("Step 3: ジオコーディング中...")

cache = {}
if CACHE_FILE.exists():
    with open(CACHE_FILE, encoding="utf-8") as f:
        cache = json.load(f)
    print(f"  キャッシュ読み込み: {len(cache)}件")


def geocode(address):
    if address in cache:
        return cache[address]
    url = f"https://msearch.gsi.go.jp/address-search/AddressSearch?q={urllib.parse.quote(address)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        result = {"lon": data[0]["geometry"]["coordinates"][0],
                  "lat": data[0]["geometry"]["coordinates"][1]} if data else {"lon": None, "lat": None}
    except Exception:
        result = {"lon": None, "lat": None}
    cache[address] = result
    time.sleep(0.3)
    return result


to_geocode = {
    code: "".join(zone_address[code]) if code in zone_address else None
    for code in all_codes
}

unique_addresses = {a for a in to_geocode.values() if a and a not in cache}
total = len(unique_addresses)
print(f"  未キャッシュのアドレス: {total}件")

for done, addr in enumerate(unique_addresses, 1):
    geocode(addr)
    if done % 100 == 0:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False)
        print(f"  進捗: {done}/{total}")

with open(CACHE_FILE, "w", encoding="utf-8") as f:
    json.dump(cache, f, ensure_ascii=False)
print(f"  完了: {total}件ジオコーディング, キャッシュ保存済み")

# ── Step 4: ゾーン座標テーブルCSV出力 ──────────────────────────────────
print("Step 4: 座標テーブルを出力中...")
records = []
no_address = no_coords = 0

for code in sorted(all_codes):
    city_code, town_code = code
    addr = to_geocode.get(code)
    result = cache.get(addr, {"lon": None, "lat": None}) if addr else {"lon": None, "lat": None}
    if not addr:
        no_address += 1
    if result["lat"] is None:
        no_coords += 1
    pref_name, city_name, town_name = zone_address.get(code, ("", "", ""))
    records.append({
        "city_code": city_code, "town_code": town_code,
        "pref_name": pref_name, "city_name": city_name, "town_name": town_name,
        "address": addr or "",
        "lat": result["lat"], "lon": result["lon"],
    })

pd.DataFrame(records).to_csv(OUTPUT_FILE, index=False, encoding="utf-8-sig")
print(f"  出力: {OUTPUT_FILE}  総ゾーン数: {len(records)}  住所名なし: {no_address}件  座標取得失敗: {no_coords}件")

# ── Step 5: GeoJSON出力 ─────────────────────────────────────────────────
print("Step 5: GeoJSONを出力中...")
features = [
    {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [r["lon"], r["lat"]]},
        "properties": {k: r[k] for k in ("city_code", "town_code", "pref_name", "city_name", "town_name", "address")},
    }
    for r in records if r["lat"] is not None
]
geojson_path = DATA_DIR / "zone_coords.geojson"
with open(geojson_path, "w", encoding="utf-8") as f:
    json.dump({"type": "FeatureCollection", "features": features}, f, ensure_ascii=False, indent=2)
print(f"  出力: {geojson_path} ({len(features)}点)")
print("Done.")

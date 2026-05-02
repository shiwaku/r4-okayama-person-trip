"""
trips_full.csv から OD ペア別トリップ数を集計して GeoJSON (LineString) を出力する。

集計キー: 平休区分 × 出発地座標 × 目的地座標
集計値:
  trip_count      : 生トリップ数（行数）
  expanded_trips  : 拡大係数の合計（推計人数ベース）

座標が取得できないトリップ（県外など）は除外。

出力:
  od_lines.geojson        (< 100MB の場合)
  od_lines.parquet        (geopandas + pyarrow が使える場合、追加で出力)
"""
import os, json, sys
import pandas as pd

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
ZONES_DIR = os.path.join(DATA_DIR, "zones")
OD_DIR = os.path.join(DATA_DIR, "od")

# ── データ読み込み ─────────────────────────────────────────────────────
print("trips_full.csv 読み込み中...")
df = pd.read_csv(
    os.path.join(DATA_DIR, "trips_full.csv"),
    encoding="utf-8",
    low_memory=False,
    dtype={
        "出発地_市町村": str, "出発地_町": str,
        "目的地_市町村": str, "目的地_町": str,
    },
    usecols=[
        "平休区分",
        "出発地_市町村", "出発地_町",
        "目的地_市町村", "目的地_町",
        "拡大係数",
        "出発地緯度", "出発地経度",
        "目的地緯度", "目的地経度",
    ],
)
print(f"  {len(df):,} 行")

# 座標が取れないトリップを除外
before = len(df)
df = df.dropna(subset=["出発地緯度", "出発地経度", "目的地緯度", "目的地経度"])
print(f"  座標なし除外: {before - len(df):,} 行 → 残り {len(df):,} 行")

# 拡大係数を数値に強制変換（混在型対策）
df["拡大係数"] = pd.to_numeric(df["拡大係数"], errors="coerce")

# 出発地 = 目的地（移動なし）を除外
df = df[
    ~((df["出発地緯度"] == df["目的地緯度"]) & (df["出発地経度"] == df["目的地経度"]))
]
print(f"  同一地点除外後: {len(df):,} 行")

# ── OD 集計 ──────────────────────────────────────────────────────────
print("OD ペア集計中...")
group_keys = [
    "平休区分",
    "出発地_市町村", "出発地_町",
    "目的地_市町村", "目的地_町",
    "出発地緯度", "出発地経度",
    "目的地緯度", "目的地経度",
]
od = (
    df.groupby(group_keys, sort=False)
    .agg(
        trip_count=("拡大係数", "count"),
        expanded_trips=("拡大係数", "sum"),
    )
    .reset_index()
)
print(f"  ユニーク OD ペア数: {len(od):,}")
print(f"  trip_count 最大: {od['trip_count'].max()}, 中央値: {od['trip_count'].median():.1f}")
print(f"  expanded_trips 最大: {od['expanded_trips'].max():,.0f}")

# ── ゾーン名称を付加（zone_coords.csv から） ─────────────────────────
coords_df = pd.read_csv(
    os.path.join(ZONES_DIR, "zone_coords.csv"),
    dtype={"city_code": str, "town_code": str},
    encoding="utf-8",
    usecols=["city_code", "town_code", "pref_name", "city_name", "town_name"],
)
name_map = {
    (r.city_code, r.town_code): f"{r.city_name}{r.town_name}"
    for r in coords_df.itertuples()
}

od["origin_name"] = od.apply(
    lambda r: name_map.get((r["出発地_市町村"], r["出発地_町"]), ""), axis=1
)
od["dest_name"] = od.apply(
    lambda r: name_map.get((r["目的地_市町村"], r["目的地_町"]), ""), axis=1
)

# ── GeoJSON 出力 ──────────────────────────────────────────────────────
print("GeoJSON 出力中...")
features = []
for r in od.itertuples(index=False):
    features.append({
        "type": "Feature",
        "geometry": {
            "type": "LineString",
            "coordinates": [
                [r.出発地経度, r.出発地緯度],
                [r.目的地経度, r.目的地緯度],
            ],
        },
        "properties": {
            "day_type":       r.平休区分,
            "origin_city":    r.出発地_市町村,
            "origin_town":    r.出発地_町,
            "origin_name":    r.origin_name,
            "dest_city":      r.目的地_市町村,
            "dest_town":      r.目的地_町,
            "dest_name":      r.dest_name,
            "trip_count":     int(r.trip_count),
            "expanded_trips": float(r.expanded_trips),
        },
    })

geojson = {"type": "FeatureCollection", "features": features}
geojson_path = os.path.join(OD_DIR, "od_lines.geojson")
with open(geojson_path, "w", encoding="utf-8") as f:
    json.dump(geojson, f, ensure_ascii=False)

size_mb = os.path.getsize(geojson_path) / 1024 / 1024
print(f"  出力: {geojson_path}")
print(f"  ファイルサイズ: {size_mb:.1f} MB  フィーチャ数: {len(features):,}")

# ── GeoParquet 出力（geopandas + pyarrow が使える場合） ───────────────
try:
    import geopandas as gpd
    from shapely.geometry import LineString as SLS

    print("\nGeoParquet 出力中...")
    geometry = [
        SLS([[r.出発地経度, r.出発地緯度], [r.目的地経度, r.目的地緯度]])
        for r in od.itertuples(index=False)
    ]
    gdf = gpd.GeoDataFrame(
        od.rename(columns={
            "平休区分": "day_type",
            "出発地_市町村": "origin_city", "出発地_町": "origin_town",
            "目的地_市町村": "dest_city",   "目的地_町": "dest_town",
            "出発地緯度": "origin_lat", "出発地経度": "origin_lon",
            "目的地緯度": "dest_lat",   "目的地経度": "dest_lon",
        }),
        geometry=geometry,
        crs="EPSG:4326",
    )
    parquet_path = os.path.join(OD_DIR, "od_lines.parquet")
    gdf.to_parquet(parquet_path)
    pq_mb = os.path.getsize(parquet_path) / 1024 / 1024
    print(f"  出力: {parquet_path}  ({pq_mb:.1f} MB)")
except ImportError as e:
    print(f"\nGeoParquet スキップ（{e}）")

print("\nDone.")
print(f"\n集計サマリー:")
print(od.groupby("平休区分")[["trip_count", "expanded_trips"]].agg(["sum", "max"]).to_string())

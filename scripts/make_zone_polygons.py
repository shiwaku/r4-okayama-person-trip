"""
e-Stat 令和2年国勢調査 小地域（町丁・字等）境界データから
パーソントリップ調査ゾーン（市町村+町レベル）のポリゴンを生成する。

PT 調査の town_code と e-Stat の 大字コードは別体系のため、
KEY_CODE 直接マッチは使用せず、ゾーンコード表の町丁名で e-Stat を
名前マッチングする。

処理の流れ:
  1. e-Stat から岡山県シェープファイル（r2ka33）を読み込み（キャッシュ優先）
  2. ゾーンコード表（code_ゾーンコード.csv）から岡山県の全定義ゾーンを構築
  3. 各ゾーンを town_name × city_code で e-Stat S_NAME に名前マッチング
     - 完全一致 → 部分一致（S_NAME が town_name を含む）の順
     - マッチした e-Stat レコードをディゾルブ
  4. 名前マッチ失敗ゾーンは市区町村レベルのポリゴンで補完
  5. EPSG:4326 の GeoJSON / GeoParquet で出力

出力: data/zone_polygons.geojson / zone_polygons.parquet
"""

import io
import zipfile
import requests
import geopandas as gpd
import pandas as pd
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
CSV_DIR = DATA_DIR / "csv"
ESTAT_CACHE_DIR = DATA_DIR / "estat_r2ka33"

# e-Stat 令和2年国勢調査 小地域（岡山県・JGD2011）
ESTAT_URL = (
    "https://www.e-stat.go.jp/gis/statmap-search/data"
    "?dlserveyId=A002005212020&code=33&coordSys=2&format=shape"
    "&downloadType=5&datum=2011"
)


def load_shapefile() -> gpd.GeoDataFrame:
    shp_path = ESTAT_CACHE_DIR / "r2ka33.shp"
    if shp_path.exists():
        print(f"e-Stat キャッシュ読み込み: {shp_path}")
        gdf = gpd.read_file(str(shp_path))
        print(f"  {len(gdf)} レコード, CRS={gdf.crs}")
        return gdf

    print("e-Stat ダウンロード中...")
    r = requests.get(ESTAT_URL, timeout=120)
    r.raise_for_status()
    print(f"  {len(r.content) / 1024 / 1024:.1f} MB")
    ESTAT_CACHE_DIR.mkdir(exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        zf.extractall(str(ESTAT_CACHE_DIR))
    shp_files = list(ESTAT_CACHE_DIR.rglob("*.shp"))
    if not shp_files:
        raise RuntimeError("shpファイルが見つかりません")
    gdf = gpd.read_file(str(shp_files[0]))
    print(f"  {shp_files[0].name}: {len(gdf)} レコード, CRS={gdf.crs}")
    return gdf


def main():
    # ── ゾーンコード表から岡山県の全定義ゾーンを構築 ───────────────────
    print("ゾーンコード表読み込み中...")
    zcode = pd.read_csv(CSV_DIR / "code_ゾーンコード.csv", dtype=str, encoding="utf-8")
    zcode_ok = zcode[zcode["都道府県+\n市区町村"].str.startswith("33", na=False)].copy()
    zcode_ok["zone_key"] = (
        zcode_ok["都道府県+\n市区町村"].str.strip()
        + zcode_ok["大字・町"].str.strip().str.zfill(3)
    )
    zcode_ok["city_code"] = zcode_ok["都道府県+\n市区町村"].str.strip()
    zcode_ok["town_code"] = zcode_ok["大字・町"].str.strip()
    zcode_ok["town_name"] = zcode_ok["大字町丁目名"].str.strip()
    zcode_ok["pref_name"] = zcode_ok["都道府県名"].str.strip()
    zcode_ok["city_name"] = zcode_ok["市区町村名"].str.strip()

    # zone_key ごとに代表行（最初の丁目なし行 or 先頭行）を選択
    zone_attrs = (
        zcode_ok.groupby("zone_key", as_index=False)
        .first()[["zone_key", "city_code", "town_code", "pref_name", "city_name", "town_name"]]
        .copy()
    )
    target_keys = set(zone_attrs["zone_key"])
    print(f"岡山県定義ゾーン数: {len(target_keys)}")

    # ── e-Stat 小地域データ取得 ─────────────────────────────────────────
    gdf = load_shapefile()
    gdf["city_code_e"] = gdf["KEY_CODE"].astype(str).str[:5]
    gdf["s_name_clean"] = gdf["S_NAME"].str.strip()
    gdf_4326 = gdf.to_crs("EPSG:4326")

    # e-Stat を市区町村別に索引化
    estat_by_city: dict[str, pd.DataFrame] = {}
    for cc, grp in gdf_4326.groupby("city_code_e"):
        estat_by_city[cc] = grp.reset_index(drop=True)

    # ── 名前マッチング（全ゾーン対象） ──────────────────────────────────
    print("名前マッチング中...")
    name_rows = []
    no_match_keys = []

    for _, row in zone_attrs.iterrows():
        key = row["zone_key"]
        city_code = row["city_code"]
        town_name = row["town_name"]

        if not town_name:
            no_match_keys.append(key)
            continue

        city_df = estat_by_city.get(city_code, pd.DataFrame())
        if city_df.empty:
            no_match_keys.append(key)
            continue

        # 完全一致
        hits = city_df[city_df["s_name_clean"] == town_name]
        # 部分一致（e-Stat S_NAME が town_name を含む）
        if hits.empty:
            hits = city_df[city_df["s_name_clean"].str.contains(town_name, regex=False, na=False)]

        if not hits.empty:
            geom = hits["geometry"].union_all()
            name_rows.append({"zone_key": key, "geometry": geom})
        else:
            no_match_keys.append(key)

    gdf_name = gpd.GeoDataFrame(name_rows, crs="EPSG:4326") if name_rows else gpd.GeoDataFrame()
    matched_name = set(gdf_name["zone_key"]) if not gdf_name.empty else set()
    print(f"名前マッチ: {len(matched_name)} ゾーン")

    # ── 市区町村ポリゴンで補完 ───────────────────────────────────────────
    city_dissolved = (
        gdf_4326[["city_code_e", "geometry"]]
        .dissolve(by="city_code_e")
        .reset_index()
    )
    city_geom = dict(zip(city_dissolved["city_code_e"], city_dissolved["geometry"]))

    city_rows = []
    skip_keys = []
    for key in no_match_keys:
        geom = city_geom.get(key[:5])
        if geom is not None:
            city_rows.append({"zone_key": key, "geometry": geom})
        else:
            skip_keys.append(key)

    gdf_city = gpd.GeoDataFrame(city_rows, crs="EPSG:4326") if city_rows else gpd.GeoDataFrame()
    matched_city = set(gdf_city["zone_key"]) if not gdf_city.empty else set()
    print(f"市区町村ポリゴン補完: {len(matched_city)} ゾーン")
    if skip_keys:
        print(f"スキップ: {len(skip_keys)} ゾーン")

    # ── 結合 ────────────────────────────────────────────────────────────
    parts = []
    if not gdf_name.empty:
        parts.append(gdf_name[["zone_key", "geometry"]])
    if not gdf_city.empty:
        parts.append(gdf_city[["zone_key", "geometry"]])

    gdf_combined = gpd.GeoDataFrame(
        pd.concat(parts, ignore_index=True), crs="EPSG:4326"
    )

    # ── 属性結合・出力列整理 ───────────────────────────────────────────
    gdf_out = gdf_combined.merge(
        zone_attrs[["zone_key", "city_code", "town_code", "pref_name", "city_name", "town_name"]],
        on="zone_key",
        how="left",
    )
    gdf_out["polygon_source"] = gdf_out["zone_key"].apply(
        lambda k: "name" if k in matched_name else "city"
    )
    gdf_out = gdf_out[[
        "zone_key", "city_code", "town_code",
        "pref_name", "city_name", "town_name",
        "polygon_source", "geometry",
    ]]

    geojson_path = DATA_DIR / "zone_polygons.geojson"
    gdf_out.to_file(str(geojson_path), driver="GeoJSON")

    parquet_path = DATA_DIR / "zone_polygons.parquet"
    gdf_out.to_parquet(str(parquet_path))

    print(f"\n出力:")
    print(f"  {geojson_path}  ({geojson_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  {parquet_path}  ({parquet_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  name  : {(gdf_out['polygon_source']=='name').sum()} ゾーン（町丁名マッチ）")
    print(f"  city  : {(gdf_out['polygon_source']=='city').sum()} ゾーン（市区町村ポリゴン補完）")
    print(f"  合計  : {len(gdf_out)} ゾーン（目標: {len(target_keys)}）")

    still_missing = target_keys - set(gdf_out["zone_key"])
    if still_missing:
        print(f"\n補完不可（スキップ）: {len(still_missing)} 件")
        m = zone_attrs[zone_attrs["zone_key"].isin(still_missing)][["zone_key", "city_name", "town_name"]]
        print(m.to_string(index=False))


if __name__ == "__main__":
    main()

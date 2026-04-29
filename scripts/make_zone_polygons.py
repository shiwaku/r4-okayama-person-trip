"""
e-Stat 令和2年国勢調査 小地域（町丁・字等）境界データから
パーソントリップ調査ゾーン（市町村+町レベル）のポリゴンを生成する。

処理の流れ:
  1. e-Stat から岡山県シェープファイル（r2ka33）をダウンロード
  2. zone_coords.csv の zone_key と KEY_CODE 先頭8桁でマッチング（一次）
  3. 未マッチゾーンを (市区町村コード, 町丁名) の名前マッチングで補完（二次）
     - e-Stat S_NAME との完全一致 → 部分一致の順で試行
  4. それでも残る未マッチには市区町村ポリゴンを割り当て
  5. EPSG:4326 の GeoJSON / GeoParquet で出力

KEY_CODE構造（e-Stat）:
  33101001001 = 都道府県(33) + 市区町村(101) + 大字(001) + 丁目(001)
  zone_key = KEY_CODE[:8] = city_code(5桁) + town_code(3桁ゼロ埋め)

出力: data/zone_polygons.geojson / zone_polygons.parquet
"""

import io
import zipfile
import tempfile
import requests
import geopandas as gpd
import pandas as pd
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
CSV_DIR = DATA_DIR / "csv"

# e-Stat 令和2年国勢調査 小地域（岡山県・JGD2011）
ESTAT_URL = (
    "https://www.e-stat.go.jp/gis/statmap-search/data"
    "?dlserveyId=A002005212020&code=33&coordSys=2&format=shape"
    "&downloadType=5&datum=2011"
)


def download_shapefile(url: str) -> gpd.GeoDataFrame:
    print("e-Stat ダウンロード中...")
    r = requests.get(url, timeout=120)
    r.raise_for_status()
    print(f"  {len(r.content) / 1024 / 1024:.1f} MB")
    with tempfile.TemporaryDirectory() as tmpdir:
        with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
            zf.extractall(tmpdir)
        shp_files = list(Path(tmpdir).rglob("*.shp"))
        if not shp_files:
            raise RuntimeError("shpファイルが見つかりません")
        gdf = gpd.read_file(str(shp_files[0]))
    print(f"  {shp_files[0].name}: {len(gdf)} レコード, CRS={gdf.crs}")
    return gdf


def main():
    # ── zone_coords.csv 読み込み ────────────────────────────────────────
    zone_df = pd.read_csv(
        DATA_DIR / "zone_coords.csv",
        dtype={"city_code": str, "town_code": str},
        encoding="utf-8",
    )
    zone_df["zone_key"] = zone_df["city_code"] + zone_df["town_code"].str.zfill(3)
    zone_attrs = (
        zone_df.groupby("zone_key", as_index=False)
        .first()[["zone_key", "city_code", "town_code", "pref_name", "city_name", "town_name", "lat", "lon"]]
    )
    target_keys = set(zone_attrs["zone_key"])
    print(f"PT調査ゾーン数: {len(target_keys)}")

    # ── ゾーンコード表から町丁名ルックアップを構築 ─────────────────────
    zcode_df = pd.read_csv(
        CSV_DIR / "code_ゾーンコード.csv", dtype=str, encoding="utf-8"
    )
    zcode_ok = zcode_df[
        zcode_df["都道府県+\n市区町村"].str.startswith("33", na=False)
    ].copy()
    zcode_ok["zone_key"] = (
        zcode_ok["都道府県+\n市区町村"].str.strip()
        + zcode_ok["大字・町"].str.strip().str.zfill(3)
    )
    zcode_ok["town_name_z"] = zcode_ok["大字町丁目名"].str.strip()
    zone_townname = (
        zcode_ok.drop_duplicates(subset="zone_key")
        .set_index("zone_key")["town_name_z"]
        .to_dict()
    )

    # ── e-Stat 小地域データ取得 ─────────────────────────────────────────
    gdf = download_shapefile(ESTAT_URL)
    gdf["zone_key"] = gdf["KEY_CODE"].astype(str).str[:8]
    gdf["city_code_e"] = gdf["KEY_CODE"].astype(str).str[:5]
    gdf["s_name_clean"] = gdf["S_NAME"].str.strip()
    gdf_4326 = gdf.to_crs("EPSG:4326")

    # ── 一次マッチング: KEY_CODE 先頭8桁 ────────────────────────────────
    gdf_m1 = gdf_4326[gdf_4326["zone_key"].isin(target_keys)].copy()
    gdf_d1 = (
        gdf_m1[["zone_key", "geometry"]]
        .dissolve(by="zone_key")
        .reset_index()
    )
    matched1 = set(gdf_d1["zone_key"])
    print(f"一次マッチ（KEY_CODE前8桁）: {len(gdf_d1)} ゾーン")

    # ── 二次マッチング: 市区町村コード + 町丁名 ─────────────────────────
    missing1 = {k for k in target_keys if k not in matched1 and k.startswith("33")}

    # e-Stat を市区町村別に索引化
    estat_by_city: dict[str, pd.DataFrame] = {}
    for cc, grp in gdf_4326.groupby("city_code_e"):
        estat_by_city[cc] = grp.reset_index(drop=True)

    name_rows = []
    no_name_match = []

    for key in sorted(missing1):
        city_code = key[:5]
        town_name = zone_townname.get(key, "")
        if not town_name:
            no_name_match.append(key)
            continue

        city_df = estat_by_city.get(city_code, pd.DataFrame())
        if city_df.empty:
            no_name_match.append(key)
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
            no_name_match.append(key)

    gdf_d2 = gpd.GeoDataFrame(name_rows, crs="EPSG:4326") if name_rows else gpd.GeoDataFrame()
    matched2 = set(gdf_d2["zone_key"]) if not gdf_d2.empty else set()
    print(f"二次マッチ（町丁名）        : {len(matched2)} ゾーン")

    # ── 三次マッチング: 市区町村ポリゴンで補完 ──────────────────────────
    city_dissolved = (
        gdf_4326[["city_code_e", "geometry"]]
        .dissolve(by="city_code_e")
        .reset_index()
    )
    city_geom = dict(zip(city_dissolved["city_code_e"], city_dissolved["geometry"]))

    city_rows = []
    skip_keys = []
    for key in no_name_match:
        city_code = key[:5]
        geom = city_geom.get(city_code)
        if geom is not None:
            city_rows.append({"zone_key": key, "geometry": geom})
        else:
            skip_keys.append(key)

    gdf_d3 = gpd.GeoDataFrame(city_rows, crs="EPSG:4326") if city_rows else gpd.GeoDataFrame()
    matched3 = set(gdf_d3["zone_key"]) if not gdf_d3.empty else set()
    print(f"三次マッチ（市区町村ポリゴン）: {len(matched3)} ゾーン")

    if skip_keys:
        print(f"スキップ（ポリゴンなし）     : {len(skip_keys)} ゾーン")

    # ── 結合 ────────────────────────────────────────────────────────────
    parts = [gdf_d1[["zone_key", "geometry"]]]
    if not gdf_d2.empty:
        parts.append(gdf_d2[["zone_key", "geometry"]])
    if not gdf_d3.empty:
        parts.append(gdf_d3[["zone_key", "geometry"]])

    gdf_combined = gpd.GeoDataFrame(
        pd.concat(parts, ignore_index=True), crs="EPSG:4326"
    )

    # ── 属性結合・出力列整理 ───────────────────────────────────────────
    gdf_out = gdf_combined.merge(
        zone_attrs[["zone_key", "city_code", "town_code", "pref_name", "city_name", "town_name"]],
        on="zone_key",
        how="left",
    )

    def _source(k):
        if k in matched1:
            return "e-stat"
        if k in matched2:
            return "name"
        return "city"

    gdf_out["polygon_source"] = gdf_out["zone_key"].apply(_source)
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
    print(f"  e-stat  : {(gdf_out['polygon_source']=='e-stat').sum()} ゾーン（KEY_CODE直接マッチ）")
    print(f"  name    : {(gdf_out['polygon_source']=='name').sum()} ゾーン（町丁名マッチ）")
    print(f"  city    : {(gdf_out['polygon_source']=='city').sum()} ゾーン（市区町村ポリゴン補完）")
    print(f"  合計    : {len(gdf_out)} ゾーン（目標: {len(target_keys)}）")

    still_missing = target_keys - set(gdf_out["zone_key"])
    if still_missing:
        print(f"\n補完不可（スキップ）: {len(still_missing)} 件")
        m = zone_attrs[zone_attrs["zone_key"].isin(still_missing)][["zone_key", "city_name", "town_name"]]
        print(m.to_string(index=False))


if __name__ == "__main__":
    main()

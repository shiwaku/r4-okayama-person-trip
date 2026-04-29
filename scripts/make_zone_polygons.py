"""
e-Stat 令和2年国勢調査 小地域（町丁・字等）境界データから
パーソントリップ調査ゾーン（市町村+町レベル）のポリゴンを生成する。

処理の流れ:
  1. e-Stat から岡山県シェープファイル（r2ka33）をダウンロード
  2. KEY_CODE 先頭8桁（都道府県+市区町村=5桁、大字=3桁）でディゾルブ
  3. zone_coords.csv の zone_key とマッチング（1392/2029ゾーン）
  4. 未マッチ637ゾーンはボロノイ分割で補完
  5. EPSG:4326 の GeoJSON で出力（全2029ゾーン）

KEY_CODE構造（e-Stat）:
  33101001001 = 都道府県(33) + 市区町村(101) + 大字(001) + 丁目(001)
  zone_key = KEY_CODE[:8] = city_code(5桁) + town_code(3桁ゼロ埋め)

出力: data/zone_polygons.geojson
"""

import io
import zipfile
import tempfile
import requests
import geopandas as gpd
import pandas as pd
from pathlib import Path
from shapely.ops import unary_union
from shapely.geometry import MultiPoint

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"

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


def make_voronoi(points_gdf: gpd.GeoDataFrame, clip_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """
    ポイントからボロノイポリゴンを生成して clip_gdf の範囲でクリップする。
    points_gdf: geometry(Point) + zone_key 列を持つ GeoDataFrame
    clip_gdf: クリップ境界の GeoDataFrame
    """
    from shapely.ops import voronoi_diagram

    all_points = MultiPoint(list(points_gdf.geometry))
    clip_geom = unary_union(clip_gdf.geometry)
    # ボロノイ生成はクリップ境界のエンベロープに拡張して精度向上
    envelope = clip_geom.buffer(0.01)
    regions = voronoi_diagram(all_points, envelope=envelope)

    rows = []
    for region in regions.geoms:
        # 最近傍ポイントのzone_keyを付与
        nearest = min(
            points_gdf.itertuples(),
            key=lambda pt: region.centroid.distance(pt.geometry),
        )
        clipped = region.intersection(clip_geom)
        if not clipped.is_empty:
            rows.append({"zone_key": nearest.zone_key, "geometry": clipped})

    return gpd.GeoDataFrame(rows, crs=points_gdf.crs)


def main():
    # ── zone_coords.csv 読み込み ────────────────────────────────────────
    zone_df = pd.read_csv(
        DATA_DIR / "zone_coords.csv",
        dtype={"city_code": str, "town_code": str},
        encoding="utf-8-sig",
    )
    zone_df["zone_key"] = zone_df["city_code"] + zone_df["town_code"].str.zfill(3)
    zone_attrs = (
        zone_df.groupby("zone_key", as_index=False)
        .first()[["zone_key", "city_code", "town_code", "pref_name", "city_name", "town_name", "lat", "lon"]]
    )
    target_keys = set(zone_attrs["zone_key"])
    print(f"PT調査ゾーン数: {len(target_keys)}")

    # ── e-Stat 小地域データ取得 ─────────────────────────────────────────
    gdf = download_shapefile(ESTAT_URL)
    gdf["zone_key"] = gdf["KEY_CODE"].astype(str).str[:8]

    # PT対象ゾーンに絞り込み・ディゾルブ（丁目 → 大字・町単位）
    gdf_matched = gdf[gdf["zone_key"].isin(target_keys)].copy()
    gdf_dissolved = (
        gdf_matched[["zone_key", "geometry"]]
        .dissolve(by="zone_key")
        .reset_index()
    )
    # EPSG:4326 に変換
    gdf_dissolved = gdf_dissolved.to_crs("EPSG:4326")
    print(f"e-Stat マッチ: {len(gdf_dissolved)} ゾーン")

    # ── 未マッチゾーンをボロノイで補完 ─────────────────────────────────
    matched_keys = set(gdf_dissolved["zone_key"])
    missing_keys = target_keys - matched_keys
    print(f"未マッチ（ボロノイ補完対象）: {len(missing_keys)} ゾーン")

    voronoi_parts = []
    if missing_keys:
        missing_attrs = zone_attrs[zone_attrs["zone_key"].isin(missing_keys)].copy()
        # 座標が取れているもののみ補完可能
        missing_with_coords = missing_attrs.dropna(subset=["lat", "lon"])
        print(f"  座標あり: {len(missing_with_coords)} / {len(missing_attrs)}")

        # 市区町村ごとにボロノイ生成（隣接市区町村への侵食を防ぐため）
        # 境界は e-Stat 全データのユニオンを市区町村別に使用
        gdf_all_4326 = gdf.to_crs("EPSG:4326")

        for city_code, grp in missing_with_coords.groupby("city_code"):
            city_boundary = gdf_all_4326[
                gdf_all_4326["zone_key"].str.startswith(city_code)
            ].copy()
            if city_boundary.empty:
                continue

            pts_gdf = gpd.GeoDataFrame(
                grp[["zone_key"]].copy(),
                geometry=gpd.points_from_xy(grp["lon"], grp["lat"]),
                crs="EPSG:4326",
            )
            try:
                v = make_voronoi(pts_gdf, city_boundary)
                voronoi_parts.append(v)
            except Exception as e:
                print(f"  ボロノイ失敗 {city_code}: {e}")

    # ── マッチ済み + ボロノイ補完 を結合 ────────────────────────────────
    parts = [gdf_dissolved[["zone_key", "geometry"]]]
    if voronoi_parts:
        parts.extend(voronoi_parts)

    gdf_combined = pd.concat(parts, ignore_index=True)

    # zone_key が重複した場合（ボロノイの最近傍問題）はディゾルブ
    gdf_combined = (
        gpd.GeoDataFrame(gdf_combined, crs="EPSG:4326")
        .dissolve(by="zone_key")
        .reset_index()
    )
    print(f"結合後ゾーン数: {len(gdf_combined)}")

    # ── 属性結合・出力列整理 ───────────────────────────────────────────
    gdf_out = gdf_combined.merge(
        zone_attrs[["zone_key", "city_code", "town_code", "pref_name", "city_name", "town_name"]],
        on="zone_key",
        how="left",
    )
    # polygon_source: e-stat=国勢調査ポリゴン、voronoi=ボロノイ補完
    gdf_out["polygon_source"] = gdf_out["zone_key"].apply(
        lambda k: "e-stat" if k in matched_keys else "voronoi"
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
    print(f"  e-stat  : {(gdf_out['polygon_source']=='e-stat').sum()} ゾーン")
    print(f"  voronoi : {(gdf_out['polygon_source']=='voronoi').sum()} ゾーン")
    print(f"  合計    : {len(gdf_out)} ゾーン（目標: {len(target_keys)}）")

    still_missing = target_keys - set(gdf_out["zone_key"])
    if still_missing:
        print(f"\n座標なしで補完不可のゾーン: {len(still_missing)} 件")
        m = zone_attrs[zone_attrs["zone_key"].isin(still_missing)][["zone_key", "city_name", "town_name"]]
        print(m.to_string(index=False))


if __name__ == "__main__":
    main()

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
     - 完全一致 → 部分一致(含む) → 先頭一致 の順
     - 正規化（括弧除去・異体字変換・丁目除去・プレフィックス除去）を多段階に適用
  4. マッチ失敗ゾーンは登記所備付地図（法務省）GeoJSON で大字名マッチ補完
  5. それでも残るゾーンは市区町村レベルのポリゴンで補完
  6. EPSG:4326 の GeoJSON / GeoParquet で出力

出力: data/zone_polygons.geojson / zone_polygons.parquet
"""

import io
import re
import zipfile
import requests
import geopandas as gpd
import pandas as pd
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
ZONES_DIR = DATA_DIR / "zones"
CSV_DIR = DATA_DIR / "csv"
ESTAT_CACHE_DIR = DATA_DIR / "estat_r2ka33"
MOJ_PARCEL_DIR = DATA_DIR / "moj_parcel"

# e-Stat 令和2年国勢調査 小地域（岡山県・JGD2011）
ESTAT_URL = (
    "https://www.e-stat.go.jp/gis/statmap-search/data"
    "?dlserveyId=A002005212020&code=33&coordSys=2&format=shape"
    "&downloadType=5&datum=2011"
)

# 登記所備付地図 2025年版 GeoJSON（G空間情報センター）
# e-Stat 名前マッチ失敗ゾーンを補完する市区町村のみ列挙
MOJ_GEOJSON_URLS: dict[str, str] = {
    "33205": (
        "https://www.geospatial.jp/ckan/dataset/81392349-8c7b-4086-a851-c45c86f2d252"
        "/resource/e0cf2499-cd1d-4eb6-b520-8a76bb391113/download/33205__5_r_2025.geojson"
    ),
    "33606": (
        "https://www.geospatial.jp/ckan/dataset/6ac6dfe8-57ad-4803-836e-a3e433b94fd0"
        "/resource/1aee32d9-3814-41a7-9e40-3130d44a5ae4/download/33606__5_r_2025.geojson"
    ),
}


# PTゾーン名→e-Stat S_NAME に向けた異体字変換テーブル
# 表記ゆれ（旧字体・旧仮名）の吸収（冶↔治は文脈依存なので別途処理）
KANJI_MAP = {
    '齋': '斎', '齊': '斉',  # 斎・斉の旧字体
    '澤': '沢',              # 沢の旧字体
    '槙': '槇',              # まき
    '曽': '曾',              # 曾の別字体
    '鍜': '鍛',              # 鍛の異体字
    '濱': '浜',              # 浜の旧字体
    '船': '舟',              # 船津→舟津（吉備中央町）
    'ヶ': 'ケ',              # 池ヶ原→池ケ原（e-Stat は通常ケ）
}


def _normalize(name: str, extra: dict | None = None) -> str:
    """括弧除去・異体字変換"""
    name = re.sub(r'[\(（][^)）]*[\)）]', '', name).strip()
    for old, new in KANJI_MAP.items():
        name = name.replace(old, new)
    if extra:
        for old, new in extra.items():
            name = name.replace(old, new)
    return name


def _strip_prefix(name: str) -> str | None:
    """旧市町村名プレフィックス除去: 鴨方町鴨方 → 鴨方"""
    m = re.match(r'^[一-鿿゠-ヿ぀-ゟ]+[市区町村](.+)$', name)
    return m.group(1) if m else None


def _strip_chome(name: str) -> str:
    """丁目番号除去: 青江六丁目 → 青江"""
    return re.sub(r'[一二三四五六七八九十百]+丁目$', '', name)


def _min_common_prefix(names: list[str]) -> str:
    """文字列リストの最小共通プレフィックスを返す"""
    if not names:
        return ""
    prefix = names[0]
    for n in names[1:]:
        i = 0
        while i < len(prefix) and i < len(n) and prefix[i] == n[i]:
            i += 1
        prefix = prefix[:i]
        if not prefix:
            break
    return prefix


def _try_match(city_df: gpd.GeoDataFrame, name: str) -> gpd.GeoDataFrame:
    """
    名前マッチング。s_name_norm（事前に normalize 済み）と比較する。

    完全一致があれば、同じ大字名で始まるサブ区画も全て union する。
    例: 「禾津」→「禾津」+「禾津三ツ家」+「禾津土居二」… を全取得。
    完全一致がなければ 部分一致 → 先頭一致（3文字以上）にフォールバック。

    1文字ゾーン名かつ完全一致なし: e-Stat が字レベル記録しか持たない大字に対応。
    startswith で候補を取得後、oaza_code 別に共通プレフィックスを計算し、
    プレフィックスがゾーン名と一致するグループのみ採用。
    例: 真庭市「上」→ oaza=034 のみ共通プレフィックス="上"（他 oaza は "上水田" 等）
    ※「北字谷口」等、大字名の直後に「字」が付く表記も許容（prefix == norm+"字"）
    """
    norm = _normalize(name)
    exact_mask = city_df["s_name_norm"] == norm
    if exact_mask.any():
        # 完全一致あり → 同じ大字名で始まるサブ区画も追加取得
        starts_mask = city_df["s_name_norm"].str.startswith(norm, na=False)
        return city_df[exact_mask | starts_mask]
    # 部分一致（3文字以上のみ: 短い名前での過剰マッチを防ぐ）
    # 例: 「上」(1文字)で contains すると真庭市の154件に誤マッチ
    if len(norm) >= 3:
        hits = city_df[city_df["s_name_norm"].str.contains(norm, regex=False, na=False)]
        if not hits.empty:
            return hits
    # 先頭一致（2文字以上: 錦織→錦織第X区 等）
    if len(norm) >= 2:
        return city_df[city_df["s_name_norm"].str.startswith(norm, na=False)]
    # 1文字ゾーン名: oaza_code 別に共通プレフィックスを確認
    if len(norm) == 1 and "oaza_code" in city_df.columns:
        sw = city_df[city_df["s_name_norm"].str.startswith(norm, na=False)]
        if not sw.empty:
            valid: list = []
            for _, grp in sw.groupby("oaza_code"):
                names = grp["s_name_norm"].dropna().tolist()
                if not names:
                    continue
                prefix = _min_common_prefix(names)
                # プレフィックスがゾーン名と一致、または ゾーン名+"字" で始まる（北字谷口 等）
                if prefix == norm or prefix.startswith(norm + "字"):
                    valid.append(grp)
            if valid:
                return gpd.GeoDataFrame(pd.concat(valid), crs=city_df.crs)
    return gpd.GeoDataFrame()


def find_name_match(city_df: gpd.GeoDataFrame, town_name: str) -> gpd.GeoDataFrame:
    """
    町名マッチングを多段階で試行する。
    1. 基本正規化（括弧除去・主要異体字変換）
    2. 丁目番号除去
    3. 旧市町村名プレフィックス除去
    4. 冶↔治 変換を追加して再試行
    """
    norm = _normalize(town_name)

    # 段階1: 正規化後
    hits = _try_match(city_df, norm)
    if not hits.empty:
        return hits

    # 段階2: 丁目除去
    chome = _strip_chome(norm)
    if chome != norm:
        hits = _try_match(city_df, chome)
        if not hits.empty:
            return hits

    # 段階3: 旧市町村名プレフィックス除去
    stripped = _strip_prefix(norm)
    if stripped:
        hits = _try_match(city_df, stripped)
        if not hits.empty:
            return hits

    # 段階4: 冶↔治 変換（新庄村 鍛冶屋→鍛治屋 等）
    for src, dst in [('冶', '治'), ('治', '冶')]:
        alt = norm.replace(src, dst)
        if alt != norm:
            hits = _try_match(city_df, alt)
            if not hits.empty:
                return hits
        # プレフィックス除去後にも適用
        if stripped:
            alt_s = stripped.replace(src, dst)
            if alt_s != stripped:
                hits = _try_match(city_df, alt_s)
                if not hits.empty:
                    return hits

    return gpd.GeoDataFrame()


def load_moj_parcels(city_code: str) -> gpd.GeoDataFrame:
    """登記所備付地図GeoJSONを読み込む（キャッシュ優先）"""
    MOJ_PARCEL_DIR.mkdir(exist_ok=True)
    cache_path = MOJ_PARCEL_DIR / f"{city_code}.geojson"
    if cache_path.exists():
        print(f"  MOJ キャッシュ: {cache_path.name}")
        return gpd.read_file(str(cache_path))
    url = MOJ_GEOJSON_URLS.get(city_code)
    if not url:
        return gpd.GeoDataFrame()
    print(f"  MOJ ダウンロード中: 市区町村コード {city_code} ...")
    r = requests.get(url, timeout=300)
    r.raise_for_status()
    cache_path.write_bytes(r.content)
    gdf = gpd.read_file(str(cache_path))
    print(f"    {len(gdf):,} 筆")
    return gdf


def find_moj_polygon(moj_gdf: gpd.GeoDataFrame, town_name: str):
    """登記所備付地図の大字名でフィルタ→dissolve してポリゴンを返す"""
    if moj_gdf.empty or "大字名" not in moj_gdf.columns:
        return None
    if "大字名_norm" not in moj_gdf.columns:
        moj_gdf = moj_gdf.copy()
        moj_gdf["大字名_norm"] = moj_gdf["大字名"].apply(
            lambda x: _normalize(x) if isinstance(x, str) else ""
        )
    norm = _normalize(town_name)
    stripped = _strip_prefix(norm)
    for candidate in ([norm] + ([stripped] if stripped else [])):
        hits = moj_gdf[moj_gdf["大字名_norm"] == candidate]
        if hits.empty:
            hits = moj_gdf[moj_gdf["大字名_norm"].str.contains(candidate, regex=False, na=False)]
        if not hits.empty:
            return hits.geometry.union_all()
    return None


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

    # zone_key ごとに代表行（属性用）と全 town_name リスト（マッチング用）を構築
    zone_attrs = (
        zcode_ok.groupby("zone_key", as_index=False)
        .first()[["zone_key", "city_code", "town_code", "pref_name", "city_name", "town_name"]]
        .copy()
    )
    # 各 zone_key に属する全丁目名リスト（重複除去・順序保持）
    zone_all_names = (
        zcode_ok.groupby("zone_key")["town_name"]
        .apply(lambda x: list(dict.fromkeys(v for v in x.dropna().str.strip() if v)))
        .reset_index()
        .rename(columns={"town_name": "town_names"})
    )
    zone_attrs = zone_attrs.merge(zone_all_names, on="zone_key", how="left")
    target_keys = set(zone_attrs["zone_key"])
    print(f"岡山県定義ゾーン数: {len(target_keys)}")

    # 市区町村ごとの全ゾーン名セット（正規化済み）
    # 末尾が町/村のゾーンの base 検索安全確認に使用
    city_zone_norm_names: dict[str, set[str]] = {}
    for cc, grp in zcode_ok.groupby("city_code"):
        nms: set[str] = set()
        for tn in grp["town_name"].dropna():
            n = _normalize(tn.strip())
            nms.add(n)
            s = _strip_prefix(n)
            if s:
                nms.add(s)
        city_zone_norm_names[cc] = nms

    # ── e-Stat 小地域データ取得 ─────────────────────────────────────────
    gdf = load_shapefile()
    gdf["city_code_e"] = gdf["KEY_CODE"].astype(str).str[:5]
    gdf["s_name_clean"] = gdf["S_NAME"].str.strip()
    gdf["s_name_norm"] = gdf["s_name_clean"].apply(
        lambda x: _normalize(x) if isinstance(x, str) else x
    )
    gdf["oaza_code"] = gdf["KEY_CODE"].astype(str).str[5:8]
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
        town_names = row["town_names"]  # 全丁目のリスト

        if not town_names:
            no_match_keys.append(key)
            continue

        city_df = estat_by_city.get(city_code, gpd.GeoDataFrame())
        if city_df.empty:
            no_match_keys.append(key)
            continue

        # 全丁目でマッチングして union（重複レコードを除く）
        all_hits = []
        seen_idx: set = set()
        for tn in town_names:
            hits = find_name_match(city_df, tn)
            if not hits.empty:
                new_hits = hits[~hits.index.isin(seen_idx)]
                if not new_hits.empty:
                    all_hits.append(new_hits)
                    seen_idx.update(new_hits.index)

        # 末尾が町/村のゾーン: base名（例: 寄島町→寄島）で始まるサブ区画を追加取得
        # 同市内に base名から始まる別ゾーンが存在する場合は適用しない（過剰マッチ防止）
        if all_hits and not city_df.empty:
            city_norms = city_zone_norm_names.get(city_code, set())
            for tn in town_names:
                norm_tn = _normalize(tn)
                stripped_tn = _strip_prefix(norm_tn)
                check_tn = stripped_tn if stripped_tn else norm_tn
                if not (check_tn.endswith(('町', '村')) and len(check_tn) >= 3):
                    continue
                base = check_tn[:-1]
                # 同市内に base で始まる別ゾーン名がある場合はスキップ
                if any(n.startswith(base) and n != check_tn for n in city_norms):
                    continue
                base_hits = city_df[city_df["s_name_norm"].str.startswith(base, na=False)]
                new_base = base_hits[~base_hits.index.isin(seen_idx)]
                if not new_base.empty:
                    all_hits.append(new_base)
                    seen_idx.update(new_base.index)

        if all_hits:
            combined = pd.concat(all_hits)
            geom = combined["geometry"].union_all()
            name_rows.append({"zone_key": key, "geometry": geom})
        else:
            no_match_keys.append(key)

    gdf_name = gpd.GeoDataFrame(name_rows, crs="EPSG:4326") if name_rows else gpd.GeoDataFrame()
    matched_name = set(gdf_name["zone_key"]) if not gdf_name.empty else set()
    print(f"名前マッチ: {len(matched_name)} ゾーン")

    # ── 登記所備付地図（法務省）で補完 ──────────────────────────────────
    if no_match_keys and MOJ_GEOJSON_URLS:
        print("登記所備付地図マッチング中...")
        moj_cache: dict[str, gpd.GeoDataFrame] = {}
        moj_rows = []
        still_no_match = []
        zone_names_map = dict(zip(zone_attrs["zone_key"], zone_attrs["town_names"]))

        for key in no_match_keys:
            city_code = key[:5]
            if city_code not in moj_cache:
                moj_cache[city_code] = load_moj_parcels(city_code)
            town_names_list = zone_names_map.get(key, [])
            geom = None
            for tn in town_names_list:
                geom = find_moj_polygon(moj_cache[city_code], tn)
                if geom is not None:
                    break
            if geom is not None:
                moj_rows.append({"zone_key": key, "geometry": geom})
            else:
                still_no_match.append(key)

        gdf_moj = gpd.GeoDataFrame(moj_rows, crs="EPSG:4326") if moj_rows else gpd.GeoDataFrame()
        matched_moj = set(gdf_moj["zone_key"]) if not gdf_moj.empty else set()
        print(f"MOJ補完: {len(matched_moj)} ゾーン")
        no_match_keys = still_no_match
    else:
        gdf_moj = gpd.GeoDataFrame()
        matched_moj: set = set()

    # ── マッチ不可ゾーン（e-Stat・MOJ どちらにも存在しない地名）──────────
    # 市区町村全体ポリゴンでの補完はしない（name マッチ済みの他ゾーンと重複するため）
    gdf_city = gpd.GeoDataFrame()
    matched_city: set = set()
    skip_keys = no_match_keys
    if skip_keys:
        print(f"マッチ不可（ポリゴンなし）: {len(skip_keys)} ゾーン")

    # ── 結合 ────────────────────────────────────────────────────────────
    parts = []
    if not gdf_name.empty:
        parts.append(gdf_name[["zone_key", "geometry"]])
    if not gdf_moj.empty:
        parts.append(gdf_moj[["zone_key", "geometry"]])
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
    def _source(k):
        if k in matched_name: return "name"
        if k in matched_moj:  return "moj"
        return "city"
    gdf_out["polygon_source"] = gdf_out["zone_key"].apply(_source)
    gdf_out = gdf_out[[
        "zone_key", "city_code", "town_code",
        "pref_name", "city_name", "town_name",
        "polygon_source", "geometry",
    ]]

    geojson_path = ZONES_DIR / "zone_polygons.geojson"
    gdf_out.to_file(str(geojson_path), driver="GeoJSON")

    parquet_path = ZONES_DIR / "zone_polygons.parquet"
    gdf_out.to_parquet(str(parquet_path))

    # ── ゾーン重心座標（zone_coords）を zone_polygons から生成 ──────────
    # 投影座標系（EPSG:6677 JGD2011 平面直角 IX 系）で重心計算後、地理座標へ戻す
    centroids = gdf_out.copy()
    centroids["geometry"] = gdf_out.to_crs("EPSG:6677").geometry.centroid.to_crs("EPSG:4326")
    centroids["lon"] = centroids.geometry.x
    centroids["lat"] = centroids.geometry.y
    gdf_coords = centroids[[
        "zone_key", "city_code", "town_code",
        "pref_name", "city_name", "town_name",
        "lat", "lon", "geometry",
    ]]

    coords_csv_path = ZONES_DIR / "zone_coords.csv"
    gdf_coords.drop(columns="geometry").to_csv(str(coords_csv_path), index=False, encoding="utf-8")

    coords_geojson_path = ZONES_DIR / "zone_coords.geojson"
    gdf_coords.to_file(str(coords_geojson_path), driver="GeoJSON")

    print(f"\n出力:")
    print(f"  {geojson_path}  ({geojson_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  {parquet_path}  ({parquet_path.stat().st_size / 1024 / 1024:.1f} MB)")
    print(f"  {coords_csv_path}  ({len(gdf_coords)} ゾーン)")
    print(f"  {coords_geojson_path}  ({len(gdf_coords)} ゾーン)")
    print(f"  name  : {(gdf_out['polygon_source']=='name').sum()} ゾーン（e-Stat 町丁名マッチ）")
    print(f"  moj   : {(gdf_out['polygon_source']=='moj').sum()} ゾーン（登記所備付地図大字名マッチ）")
    print(f"  合計  : {len(gdf_out)} ゾーン / 目標: {len(target_keys)} ゾーン")

    still_missing = target_keys - set(gdf_out["zone_key"])
    if still_missing:
        print(f"\n補完不可（スキップ）: {len(still_missing)} 件")
        m = zone_attrs[zone_attrs["zone_key"].isin(still_missing)][["zone_key", "city_name", "town_name"]]
        print(m.to_string(index=False))


if __name__ == "__main__":
    main()

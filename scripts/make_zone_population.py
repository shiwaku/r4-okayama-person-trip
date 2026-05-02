"""
PT 調査トリップデータから「ゾーン別・時刻別・滞留人口」を推計する。

アルゴリズム:
  各人のトリップ列から「在ゾーン区間」を構築し、
  毎正時（0:00〜23:00）のスナップショット人口を拡大係数で推計する。

在ゾーン区間:
  - 移動なし: (自宅, 0分, 1440分)
  - 移動あり:
      (自宅, 0, 第1トリップ出発時刻)
      (第k トリップ到着地, 第k 到着時刻, 第k+1 出発時刻)
      (最終トリップ到着地, 最終到着時刻, 1440)
  ※ 移動中（出発→到着）は在ゾーンなし

集計:
  各スナップショット時刻 h:00 (= h×60分) で区間をカバーする人の
  拡大係数を合算 → ゾーン別推計人口
  2ロット分を平均して「典型的な平日/休日」の推定値を算出

出力:
  data/zone_population.csv
  data/zone_population.parquet   (zone_polygons ポリゴン結合済み GeoParquet)
"""

import pandas as pd
import geopandas as gpd
import numpy as np
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
ZONES_DIR = DATA_DIR / "zones"


def to_minutes(ampm_s: pd.Series, h_s: pd.Series, m_s: pd.Series) -> pd.Series:
    """午前/午後・時・分 → 深夜0時からの分数。欠損は NaN。"""
    h = pd.to_numeric(h_s, errors="coerce")
    m = pd.to_numeric(m_s, errors="coerce")
    pm = ampm_s == "午後"
    am = ampm_s == "午前"
    # 午後12時=正午 → 12、午後1時=13、...
    # 午前12時=深夜0時 → 0
    hours = h.copy()
    hours = hours.where(~(pm & (h != 12)), h + 12)
    hours = hours.where(~(am & (h == 12)), 0)
    return hours * 60 + m


def zone_key(city: pd.Series, town: pd.Series) -> pd.Series:
    """city_code(5桁) + town_code(3桁ゼロ埋め)"""
    c = city.astype(str).str.strip()
    t = pd.to_numeric(town, errors="coerce").fillna(0).astype(int).astype(str).str.zfill(3)
    return c + t


def main():
    # ── データ読み込み ──────────────────────────────────────────────────────
    print("trips_full.csv 読み込み中...")
    df = pd.read_csv(
        DATA_DIR / "trips_full.csv",  # data/ 直下
        low_memory=False,
        dtype={
            "自宅住所_市町村": str, "自宅住所_町": str,
            "出発地_市町村": str, "出発地_町": str,
            "目的地_市町村": str, "目的地_町": str,
        },
        usecols=[
            "平休区分", "調査日_ロット番号", "サンプルNO", "トリップ番号",
            "移動の有無",
            "自宅住所_市町村", "自宅住所_町",
            "出発地_市町村", "出発地_町",
            "目的地_市町村", "目的地_町",
            "出発_午前1 午後2", "出発_時", "出発_分",
            "到着_午前1 午後2", "到着_時", "到着_分",
            "拡大係数",
        ],
    )
    print(f"  {len(df):,} 行")

    # 不正ロット（"*" 等）除外
    df = df[df["調査日_ロット番号"].isin(["平日10/12・休日10/16", "平日10/19・休日10/23"])].copy()

    # 時刻を分に変換
    df["depart_min"] = to_minutes(df["出発_午前1 午後2"], df["出発_時"], df["出発_分"])
    df["arrive_min"] = to_minutes(df["到着_午前1 午後2"], df["到着_時"], df["到着_分"])

    # zone_key 構築
    df["home_key"]   = zone_key(df["自宅住所_市町村"], df["自宅住所_町"])
    df["origin_key"] = zone_key(df["出発地_市町村"], df["出発地_町"])
    df["dest_key"]   = zone_key(df["目的地_市町村"], df["目的地_町"])

    # 拡大係数を数値化
    df["拡大係数"] = pd.to_numeric(df["拡大係数"], errors="coerce")

    # person_id (ロット × サンプルNO)
    df["person_id"] = df["調査日_ロット番号"].astype(str) + "_" + df["サンプルNO"].astype(str)

    # ── 在ゾーン区間を構築 ──────────────────────────────────────────────────
    print("在ゾーン区間を構築中...")

    # 移動なし: (自宅, 0, 1440)
    no_move = df[df["移動の有無"] == "無"].drop_duplicates("person_id")
    intervals_no_move = pd.DataFrame({
        "day_type":    no_move["平休区分"].values,
        "lot":         no_move["調査日_ロット番号"].values,
        "zone_key":    no_move["home_key"].values,
        "start_min":   0,
        "end_min":     1440,
        "expansion":   no_move["拡大係数"].values,
    })

    # 移動あり
    has_move = df[df["移動の有無"] == "有"].copy()
    has_move["トリップ番号"] = pd.to_numeric(has_move["トリップ番号"], errors="coerce")
    has_move = has_move.sort_values(["person_id", "トリップ番号"])

    interval_rows = []

    for pid, grp in has_move.groupby("person_id", sort=False):
        day_type  = grp["平休区分"].iloc[0]
        lot       = grp["調査日_ロット番号"].iloc[0]
        expansion = grp["拡大係数"].iloc[0]
        home      = grp["home_key"].iloc[0]

        trips = grp.reset_index(drop=True)
        n = len(trips)

        # 自宅滞在: 0 → 第1トリップ出発
        first_depart = trips.loc[0, "depart_min"]
        if pd.notna(first_depart) and first_depart > 0:
            interval_rows.append((day_type, lot, home, 0.0, first_depart, expansion))

        for i in range(n):
            arr = trips.loc[i, "arrive_min"]
            if pd.isna(arr):
                continue
            dest = trips.loc[i, "dest_key"]
            if i + 1 < n:
                next_dep = trips.loc[i + 1, "depart_min"]
                end = float(next_dep) if pd.notna(next_dep) else 1440.0
            else:
                end = 1440.0
            if arr < end:
                interval_rows.append((day_type, lot, dest, float(arr), end, expansion))

    intervals_move = pd.DataFrame(
        interval_rows,
        columns=["day_type", "lot", "zone_key", "start_min", "end_min", "expansion"],
    )

    intervals = pd.concat(
        [intervals_no_move, intervals_move],
        ignore_index=True,
    )
    intervals["start_min"] = pd.to_numeric(intervals["start_min"], errors="coerce")
    intervals["end_min"]   = pd.to_numeric(intervals["end_min"],   errors="coerce")
    intervals = intervals.dropna(subset=["start_min", "end_min", "expansion", "zone_key"])
    print(f"  区間数: {len(intervals):,}")

    # ── 時刻別スナップショット集計 ────────────────────────────────────────
    print("時刻別滞留人口を集計中...")
    hourly_rows = []
    for h in range(24):
        t = h * 60  # スナップショット時刻（分）
        mask = (intervals["start_min"] <= t) & (intervals["end_min"] > t)
        sub = intervals[mask]
        agg = (
            sub.groupby(["day_type", "lot", "zone_key"], sort=False)["expansion"]
            .sum()
            .reset_index(name="population_sum")
        )
        agg["hour"] = h
        hourly_rows.append(agg)

    hourly = pd.concat(hourly_rows, ignore_index=True)

    # ロット数で平均（2ロット → 典型的な1日の推定）
    lot_count = (
        df[["平休区分", "調査日_ロット番号"]].drop_duplicates()
        .groupby("平休区分")["調査日_ロット番号"].count()
        .rename("n_lots")
    )
    hourly = hourly.merge(
        lot_count.reset_index().rename(columns={"平休区分": "day_type"}),
        on="day_type",
    )
    hourly["population"] = hourly["population_sum"] / hourly["n_lots"]

    result = (
        hourly.groupby(["day_type", "zone_key", "hour"], sort=False)["population"]
        .sum()
        .reset_index()
    )
    result = result.sort_values(["day_type", "zone_key", "hour"]).reset_index(drop=True)

    print(f"  出力行数: {len(result):,}  (ゾーン数×24時間×平休)")
    print("\n滞留人口サンプル（岡山市北区 33101001, 平日）:")
    sample = result[(result["zone_key"] == "33101001") & (result["day_type"] == "平日")]
    print(sample[["hour", "population"]].to_string(index=False))

    # ── CSV 出力 ─────────────────────────────────────────────────────────
    csv_path = ZONES_DIR / "zone_population.csv"
    result.to_csv(str(csv_path), index=False, encoding="utf-8")
    print(f"\n出力: {csv_path}  ({csv_path.stat().st_size/1024/1024:.1f} MB)")

    # ── datetime 列追加（QGIS 時系列アニメーション用） ────────────────────
    # 平日=2022-10-12, 休日=2022-10-16 を基準日とし、hour 分のオフセットを加算
    REF_DATE = {"平日": "2022-10-12", "休日": "2022-10-16"}
    result["start_time"] = result.apply(
        lambda r: pd.Timestamp(REF_DATE[r["day_type"]]) + pd.Timedelta(hours=int(r["hour"])),
        axis=1,
    )
    result["end_time"] = result["start_time"] + pd.Timedelta(hours=1)

    # ── GeoParquet 出力（zone_polygons とジョイン、平日・休日別） ────────
    print("GeoParquet 出力中...")
    zones = gpd.read_parquet(str(ZONES_DIR / "zone_polygons.parquet"))
    gdf = zones.merge(result, on="zone_key", how="inner")

    SUFFIX = {"平日": "weekday", "休日": "holiday"}
    for day_type, suffix in SUFFIX.items():
        sub = gdf[gdf["day_type"] == day_type].copy()
        pq_path = ZONES_DIR / f"zone_population_{suffix}.parquet"
        sub.to_parquet(str(pq_path))
        print(f"出力: {pq_path}  ({pq_path.stat().st_size/1024/1024:.1f} MB)")
        print(f"  フィーチャ数: {len(sub):,}  ゾーン数: {sub['zone_key'].nunique():,}")

    # ── サマリー ──────────────────────────────────────────────────────
    print("\n── 集計サマリー ──")
    peak = result.loc[result.groupby(["day_type", "hour"])["population"].sum().reset_index()
                      .groupby("day_type")["population"].idxmax()]
    by_dayhour = result.groupby(["day_type", "hour"])["population"].sum().reset_index()
    print(by_dayhour.groupby("day_type").apply(
        lambda x: x.nlargest(3, "population")[["hour", "population"]].assign(rank=range(1, 4))
    ).to_string())


if __name__ == "__main__":
    main()

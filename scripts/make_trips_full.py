"""
マスターデータ（平日・休日）の全列に座標を付加し、コード値を読み替えてCSV出力する。

入力:
  data/csv/01_master_weekday.csv
  data/csv/02_master_holiday.csv
  data/csv/code_ターミナルコード.csv
  data/zone_coords.csv

出力:
  data/trips_full.csv
"""
import pandas as pd
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"
CSV_DIR = DATA_DIR / "csv"

# ── コード定義 ────────────────────────────────────────────────────────────
SURVEY_DATE = {1: "平日10/12・休日10/16", 2: "平日10/19・休日10/23"}
GENDER      = {1: "男性", 2: "女性"}
EMPLOYMENT  = {
    1: "会社員等", 2: "自営(自宅)", 3: "自営(自宅外)",
    4: "農林水産", 5: "主婦(夫)", 6: "生徒・学生", 7: "無職", 9: "未記入",
}
LICENSE  = {1: "自動車", 2: "二輪・原付", 3: "自主返納", 4: "なし", 9: "未記入"}
HAS_CAR  = {1: "有", 2: "無", 9: "未記入"}
HAS_TRIP = {1: "有", 2: "無"}
FACILITY = {
    1: "住宅・寮", 2: "学校等", 3: "文化・宗教", 4: "医療・福祉",
    5: "事務所・会社", 6: "官公庁", 7: "問屋・卸売", 8: "商業施設",
    9: "飲食店", 10: "宿泊・娯楽", 11: "工場・倉庫", 12: "交通・運輸",
    13: "農林漁業", 14: "その他", 99: "未記入",
}
PURPOSE = {
    1: "出勤", 2: "登校", 3: "業務", 4: "買物",
    5: "通院", 6: "私用", 7: "帰宅", 8: "その他", 9: "未記入",
}
MODE = {
    1: "徒歩", 2: "自転車", 3: "バイク",
    4: "自動車(運転)", 5: "自動車(同乗)",
    6: "路線バス", 7: "貸切バス", 8: "鉄道",
    9: "路面電車", 10: "タクシー", 11: "デマンドタクシー",
    12: "船舶・飛行機", 13: "その他", 99: "未記入",
}
AGE_GROUP = {
    4: "15-17歳", 5: "18-19歳", 6: "20-24歳", 7: "25-29歳",
    8: "30-34歳", 9: "35-39歳", 10: "40-44歳", 11: "45-49歳",
    12: "50-54歳", 13: "55-59歳", 14: "60-64歳", 15: "65-69歳",
    16: "70-74歳", 17: "75-79歳", 18: "80-84歳", 19: "85-89歳",
    20: "90-94歳", 21: "95歳-",
}
TIME_ZONE = {
    1: "朝ピーク(7-9時)", 2: "オフピーク(9-16時)",
    3: "夕ピーク(16-19時)", 4: "その他(-7時・19時-)", 9: "不明",
}
AM_PM = {1: "午前", 2: "午後"}

# 列名 → 変換マッピング
CODE_MAP = {
    "調査日_ロット番号":    SURVEY_DATE,
    "性別":               GENDER,
    "就業・就学状況":      EMPLOYMENT,
    "免許の有無":          LICENSE,
    "自由に使える自動車":  HAS_CAR,
    "移動の有無":          HAS_TRIP,
    "出発地_施設の種類":   FACILITY,
    "目的地_施設の種類":   FACILITY,
    "出発_午前1 午後2":   AM_PM,
    "到着_午前1 午後2":   AM_PM,
    "移動目的":            PURPOSE,
    "交通手段_①":         MODE,
    "交通手段_②":         MODE,
    "交通手段_③":         MODE,
    "交通手段_④":         MODE,
    "交通手段_⑤":         MODE,
    "年齢階層コード":      AGE_GROUP,
    "代表交通手段":        MODE,
    "時間帯コード":        TIME_ZONE,
}

TERMINAL_COLS = [
    "利用ターミナル_利用した駅、電停、バス停_①",
    "利用ターミナル_②", "利用ターミナル_③",
    "利用ターミナル_④", "利用ターミナル_⑤", "利用ターミナル_⑥",
]


def cv(mapping, val):
    if pd.isna(val):
        return None
    try:
        return mapping.get(int(val), val)
    except (ValueError, TypeError):
        return val


def safe_code(v):
    if pd.isna(v) or str(v) in ("*", "None", ""):
        return None
    try:
        return str(int(float(v)))
    except (ValueError, TypeError):
        return None


# ── ターミナルコード ──────────────────────────────────────────────────────
print("ターミナルコード読み込み中...")
term_df = pd.read_csv(CSV_DIR / "code_ターミナルコード.csv", encoding="utf-8-sig")
terminal = dict(zip(term_df.iloc[:, 0].astype(int), term_df.iloc[:, 1].astype(str)))
print(f"  {len(terminal)} ターミナル")

# ── 座標ルックアップ ─────────────────────────────────────────────────────
print("座標ルックアップ読み込み中...")
coords_df = pd.read_csv(
    DATA_DIR / "zone_coords.csv",
    dtype={"city_code": str, "town_code": str},
    encoding="utf-8-sig",
)
coords = {(r.city_code, r.town_code): (r.lat, r.lon) for r in coords_df.itertuples()}
print(f"  {len(coords)} ゾーン")


# ── データ処理 ───────────────────────────────────────────────────────────
def process(path: Path, day_type: str) -> pd.DataFrame:
    print(f"\n{day_type} 読み込み中: {path.name}")
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str)
    df.insert(0, "平休区分", day_type)

    # コード値 → ラベル
    for col, mapping in CODE_MAP.items():
        if col in df.columns:
            df[col] = df[col].apply(lambda v: cv(mapping, v))

    # ターミナルコード → 名称
    for col in TERMINAL_COLS:
        if col in df.columns:
            def _term(v):
                if pd.isna(v) or str(v).strip() in ("", "nan", "*"):
                    return None
                try:
                    return terminal.get(int(float(v)), v)
                except (ValueError, TypeError):
                    return v
            df[col] = df[col].apply(_term)

    # 県内フラグ（● = 県内、空 = 県外）
    for col in ("発地_県内フラグ", "着地_県内フラグ"):
        if col in df.columns:
            df[col] = df[col].apply(
                lambda v: "県内" if v == "●" else ("県外" if pd.isna(v) or str(v).strip() == "" else v)
            )

    # 座標結合
    o_keys = df["出発地_市町村"].apply(safe_code).str.cat(df["出発地_町"].apply(safe_code), sep="__")
    d_keys = df["目的地_市町村"].apply(safe_code).str.cat(df["目的地_町"].apply(safe_code), sep="__")

    coord_map = {f"{c}__{t}": (lat, lon) for (c, t), (lat, lon) in coords.items()}

    df["出発地緯度"]  = o_keys.map(lambda k: coord_map.get(k, (None, None))[0])
    df["出発地経度"]  = o_keys.map(lambda k: coord_map.get(k, (None, None))[1])
    df["目的地緯度"]  = d_keys.map(lambda k: coord_map.get(k, (None, None))[0])
    df["目的地経度"]  = d_keys.map(lambda k: coord_map.get(k, (None, None))[1])

    miss_o = df["出発地緯度"].isna().sum()
    miss_d = df["目的地緯度"].isna().sum()
    print(f"  {len(df):,} 行  座標なし: 出発地 {miss_o}件, 目的地 {miss_d}件")
    return df


dfs = []
for fname, day_type in [
    ("01_master_weekday.csv", "平日"),
    ("02_master_holiday.csv", "休日"),
]:
    dfs.append(process(CSV_DIR / fname, day_type))

print("\nCSV出力中...")
df_all = pd.concat(dfs, ignore_index=True)
out_path = DATA_DIR / "trips_full.csv"
df_all.to_csv(out_path, index=False, encoding="utf-8-sig")
print(f"出力完了: {out_path}")
print(f"総トリップ数: {len(df_all):,} 行  列数: {len(df_all.columns)}")

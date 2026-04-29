"""
Excel → CSV 一括変換スクリプト

出力先: data/csv/
  01_master_weekday.csv      平日マスターデータ（行11〜）
  02_master_holiday.csv      休日マスターデータ（行11〜）
  code_調査日ロット番号.csv
  code_性別.csv
  code_就業就学状況.csv
  code_自動車免許.csv
  code_自由に使える自動車.csv
  code_移動の有無.csv
  code_施設の種類.csv
  code_移動目的.csv
  code_交通手段.csv
  code_代表交通手段.csv
  code_年齢階層.csv
  code_時間帯コード.csv
  code_午前午後.csv
  code_ゾーンコード.csv
  code_ターミナルコード.csv
"""

import pandas as pd
import openpyxl
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
SOURCE_DIR = ROOT_DIR / "source"
DATA_DIR = ROOT_DIR / "data"
CSV_DIR = DATA_DIR / "csv"
CSV_DIR.mkdir(exist_ok=True)


# ── マスターデータ ──────────────────────────────────────────────────────────

def convert_master(fname: str, out_name: str):
    path = SOURCE_DIR / fname
    print(f"{fname} → {out_name} ...")
    df = pd.read_excel(path, header=None, skiprows=10, dtype=str)
    # A列・B列（index 0,1）は常に空なので除去
    df = df.drop(columns=[0, 1])
    df.to_csv(CSV_DIR / out_name, index=False, header=False, encoding="utf-8")
    print(f"  {len(df)} 行, {len(df.columns)} 列")


# ── コード表: 指定セル範囲を抜き出してCSV化 ─────────────────────────────────

def extract_table(ws, title: str, out_name: str, header_row: int, data_row_start: int,
                  data_row_end: int, col_start: int, col_end: int):
    """
    ws: openpyxl worksheet
    header_row, data_row_*: 1-indexed行番号
    col_start, col_end: 1-indexed列番号
    """
    def row_vals(r):
        return [ws.cell(row=r, column=c).value for c in range(col_start, col_end + 1)]

    headers = row_vals(header_row)
    rows = [row_vals(r) for r in range(data_row_start, data_row_end + 1)
            if any(v is not None for v in row_vals(r))]

    df = pd.DataFrame(rows, columns=headers)
    df.to_csv(CSV_DIR / out_name, index=False, encoding="utf-8")
    print(f"  {title}: {len(df)} 行 → {out_name}")


def convert_code_tables():
    path = SOURCE_DIR / "03_コード表.xlsx"
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)

    # ── コード表シート ──────────────────────────────────────────────────────
    ws = wb["コード表"]
    print("コード表シート:")

    # A-B列グループ
    extract_table(ws, "調査日ロット番号",    "code_調査日ロット番号.csv",    4,  5,  6,  1, 2)
    extract_table(ws, "性別",               "code_性別.csv",               9, 10, 11,  1, 2)
    extract_table(ws, "就業就学状況",        "code_就業就学状況.csv",       14, 15, 22,  1, 2)
    extract_table(ws, "自動車免許",          "code_自動車免許.csv",         25, 26, 30,  1, 2)
    extract_table(ws, "自由に使える自動車",  "code_自由に使える自動車.csv", 33, 34, 36,  1, 2)
    extract_table(ws, "移動の有無",          "code_移動の有無.csv",         39, 40, 41,  1, 2)
    extract_table(ws, "交通手段",            "code_交通手段.csv",           44, 45, 58,  1, 2)

    # D-E列グループ
    extract_table(ws, "施設の種類",  "code_施設の種類.csv",  4,  5, 19,  4, 5)
    extract_table(ws, "移動目的",    "code_移動目的.csv",   22, 23, 31,  4, 5)
    extract_table(ws, "時間帯コード","code_時間帯コード.csv",34, 35, 39,  4, 5)

    # D-F列（代表交通手段は3列）
    extract_table(ws, "代表交通手段","code_代表交通手段.csv",44, 45, 58,  4, 6)

    # G-H列グループ
    extract_table(ws, "年齢階層",   "code_年齢階層.csv",    4,  5, 22,  7, 8)
    extract_table(ws, "午前午後",   "code_午前午後.csv",   35, 36, 39,  7, 8)

    # ── ゾーンコード表シート ───────────────────────────────────────────────
    ws2 = wb["ｿﾞｰﾝｺｰﾄﾞ表"]
    print("ゾーンコード表シート:")

    # 列数を確認
    max_col = 0
    for row in ws2.iter_rows(min_row=8, max_row=8, values_only=False):
        for cell in row:
            if cell.value is not None:
                max_col = max(max_col, cell.column)

    headers = [ws2.cell(row=8, column=c).value for c in range(1, max_col + 1)]
    rows = []
    for r in ws2.iter_rows(min_row=10, values_only=True):
        vals = list(r[:max_col])
        if any(v is not None for v in vals):
            rows.append(vals)

    df_zone = pd.DataFrame(rows, columns=headers)
    df_zone.to_csv(CSV_DIR / "code_ゾーンコード.csv", index=False, encoding="utf-8")
    print(f"  ゾーンコード: {len(df_zone)} 行 → code_ゾーンコード.csv")

    # ── ターミナルコード表シート ───────────────────────────────────────────
    ws3 = wb["ターミナルコード表"]
    print("ターミナルコード表シート:")

    # C列〜H列（コード4桁〜備考）
    headers_t = [ws3.cell(row=2, column=c).value for c in range(3, 9)]
    rows_t = []
    for r in ws3.iter_rows(min_row=3, values_only=True):
        vals = list(r[2:8])
        if any(v is not None for v in vals):
            rows_t.append(vals)

    df_term = pd.DataFrame(rows_t, columns=headers_t)
    df_term.to_csv(CSV_DIR / "code_ターミナルコード.csv", index=False, encoding="utf-8")
    print(f"  ターミナルコード: {len(df_term)} 行 → code_ターミナルコード.csv")

    wb.close()


if __name__ == "__main__":
    print("=== マスターデータ変換 ===")
    convert_master("01_R4岡山PTマスターデータ平日.xlsx", "01_master_weekday.csv")
    convert_master("02_R4岡山PTマスターデータ休日.xlsx", "02_master_holiday.csv")

    print("\n=== コード表変換 ===")
    convert_code_tables()

    print(f"\n完了: {CSV_DIR}")

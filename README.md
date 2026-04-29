# 岡山県パーソントリップ調査マスターデータ

令和4年（2022年）実施の岡山県パーソントリップ調査のマスターデータを処理するスクリプト・出力データ集。

- 対象人口: 1,571,431人（R4.10月時点の15歳以上）
- 調査日: 平日 10/12・10/19、休日 10/16・10/23
- 回収票数: 平日 27,395票（標本率1.74%）、休日 27,228票（標本率1.73%）

データ出典: [おかやまオープンデータカタログ](https://www.okayama-opendata.jp/datasets/6694)

> 「岡山県パーソントリップ調査」（おかやまオープンデータカタログ）を加工して作成

---

## ディレクトリ構成

```
/
├── source/                        # 原本データ
│   ├── 01_R4岡山PTマスターデータ平日.xlsx
│   ├── 02_R4岡山PTマスターデータ休日.xlsx
│   ├── 03_コード表.xlsx
│   └── 04_拡大係数の設定.pdf
├── scripts/
│   ├── convert_to_csv.py          # Excel → CSV 一括変換
│   ├── make_trips_full.py         # トリップデータ生成
│   ├── make_od_lines.py           # OD集計・GeoJSON/Parquet生成
│   ├── make_zone_polygons.py      # ゾーンポリゴン＋重心座標生成
│   └── make_zone_population.py    # ゾーン別時刻別滞留人口推計
├── data/
│   ├── csv/                       # CSV変換出力
│   │   ├── code_*.csv             # コード表（15ファイル）
│   │   ├── 01_master_weekday.csv  # 平日マスターデータ ※gitignore
│   │   └── 02_master_holiday.csv  # 休日マスターデータ ※gitignore
│   ├── zone_coords.csv                    # ゾーン重心座標対応表（2,208ゾーン）
│   ├── zone_coords.geojson                # 同上 GeoJSON（Point）
│   ├── zone_polygons.parquet              # ゾーンポリゴン GeoParquet（8.6MB）
│   ├── od_lines.parquet                   # OD集計 GeoParquet（1.4MB）
│   ├── zone_population.csv                # ゾーン別時刻別滞留人口（2.1MB）
│   ├── zone_population_weekday.parquet    # 同上 平日 + ゾーンポリゴン結合 GeoParquet（52.4MB）
│   ├── zone_population_holiday.parquet    # 同上 休日 + ゾーンポリゴン結合 GeoParquet（51.0MB）
│   ├── od_lines.qml               # 生トリップ数スタイル（QGISから参照）
│   ├── od_lines_expanded.qml      # 拡大係数適用スタイル（QGISから参照）
│   ├── zone_population.qml          # 滞留人口スタイル・時系列アニメーション設定（共通定義）
   ├── zone_population_weekday.qml  # 同上 平日用（zone_population_weekday.parquet に自動適用）
   ├── zone_population_holiday.qml  # 同上 休日用（zone_population_holiday.parquet に自動適用）
│   ├── trips_full.csv             # 全トリップCSV ※gitignore
│   ├── od_lines.geojson           # OD集計 GeoJSON ※gitignore
│   ├── zone_polygons.geojson      # ゾーンポリゴン GeoJSON ※gitignore
│   └── geocode_cache.json         # ジオコーディングキャッシュ ※gitignore
└── qgis/                          # QGISプロジェクト ※gitignore
    └── Map.qgz
```

データ出典: [おかやまオープンデータカタログ](https://www.okayama-opendata.jp/datasets/6694)

---

## スクリプトの実行順

```bash
# 依存ライブラリのインストール
pip install openpyxl pandas geopandas pyarrow requests shapely

# 1. コード表・マスターデータを CSV に変換
python scripts/convert_to_csv.py

# 2. 全トリップCSV生成（1の完了後）
python scripts/make_trips_full.py

# 3. OD集計・GeoJSON/GeoParquet生成
python scripts/make_od_lines.py

# 4. ゾーンポリゴン＋重心座標生成（e-Stat自動ダウンロード・ネット接続必要）
python scripts/make_zone_polygons.py

# 5. ゾーン別時刻別滞留人口推計（2の完了後）
python scripts/make_zone_population.py
```

---

## データ仕様

### data/csv/code_*.csv（コード表）

`03_コード表.xlsx` の各表を1ファイルに変換したもの。

| ファイル | 内容 |
|---|---|
| `code_調査日ロット番号.csv` | E列コード |
| `code_性別.csv` | F列コード |
| `code_就業就学状況.csv` | I列コード |
| `code_自動車免許.csv` | J列コード |
| `code_自由に使える自動車.csv` | K列コード |
| `code_移動の有無.csv` | L列コード |
| `code_施設の種類.csv` | P・S列コード |
| `code_移動目的.csv` | Z列コード |
| `code_交通手段.csv` | AA〜AE列コード |
| `code_代表交通手段.csv` | AO列コード（優先順位付き） |
| `code_年齢階層.csv` | AN列コード |
| `code_時間帯コード.csv` | AP列コード |
| `code_午前午後.csv` | T・W列コード |
| `code_ゾーンコード.csv` | 住所コード ↔ ゾーンコード対応表（2,790件） |
| `code_ターミナルコード.csv` | バス停・駅・電停等コード（7,515件） |

### zone_polygons.parquet（GeoParquet）

| フィールド | 内容 |
|---|---|
| `zone_key` | city_code(5桁) + town_code(3桁ゼロ埋め) の8桁キー |
| `city_code` / `town_code` | 市区町村コード・大字町コード |
| `city_name` / `town_name` | 市区町村名・大字町名 |
| `polygon_source` | `name`=e-Stat 町丁名マッチ（2,206件）、`moj`=登記所備付地図大字名マッチ（2件） |

e-Stat 令和2年国勢調査 小地域データを主ソースとし、名前マッチングで取得。マッチング手順:
1. e-Stat S_NAME との名前マッチ（括弧除去・異体字正規化・旧市町村名プレフィックス除去・丁目番号除去の多段階正規化）（2,206件）
   - 複数丁目ゾーン（例: 中山下一丁目+二丁目）はすべての丁目を union
   - 大字サブ区画（禾津→禾津三ツ家・禾津土居二 等）も startswith で一括 union
   - 「X町」形式かつ同市内に競合ゾーンがない場合は「X新開」等の関連サブ区画も追加取得
   - 1文字ゾーン名（上・関・惣・種・中・吉・石・奥・北・西 等）: e-Stat に大字単体レコードがない場合、oaza_code 別に字レベルレコードの共通プレフィックスを確認し大字相当グループを特定
2. e-Stat に存在しない地名は登記所備付地図（法務省）GeoJSON の大字名マッチで補完（2件）

3件（津山市加茂町齋野谷、高梁市川上町吉木、新庄村長床）と124件（県外・都道府県単位ゾーン）はポリゴンなし。

### zone_coords.csv

| 列 | 内容 |
|---|---|
| `city_code` | 市区町村コード（5桁） |
| `town_code` | 大字・町コード（整数） |
| `pref_name` / `city_name` / `town_name` | 住所名 |
| `lat` / `lon` | 緯度・経度（国土地理院APIで取得） |

### zone_population.csv / zone_population_weekday.parquet / zone_population_holiday.parquet

各ゾーンの毎正時スナップショット滞留人口（拡大係数適用・2ロット平均）。

| フィールド | 内容 |
|---|---|
| `day_type` | 平日 / 休日 |
| `zone_key` | 8桁ゾーンキー |
| `hour` | 時刻（0〜23）。h時 = h:00 時点のスナップショット |
| `population` | 推計滞留人口（拡大係数合計 ÷ ロット数） |
| `start_time` | QGIS時系列用（例: 2022-10-12 14:00:00） |
| `end_time` | QGIS時系列用（start_time + 1時間） |

- GeoParquetは平日・休日を別ファイルに分割（zone_polygons のポリゴン属性を結合済み）
  - `zone_population_weekday.parquet`: 平日 2,013ゾーン × 24時間 = 44,451行（52.4MB）
  - `zone_population_holiday.parquet`: 休日 1,896ゾーン × 24時間 = 42,533行（51.0MB）
- 在ゾーン判定: 到着時刻 ≤ h:00 < 次の出発時刻（移動中は未カウント）
- 移動なし（移動の有無=無）は自宅ゾーンに24時間計上
- 2ロット（10/12+10/19 または 10/16+10/23）の平均値

#### 在ゾーン判定のイメージ

```
時刻(分)  0     400   480  510        720  760        810  870        1440
          |      |     |    |           |    |           |    |           |
行動      [自宅滞在]  移動  [職場B 滞在]  移動  [商業C 滞在]  移動  [自宅A 滞在 ]
                  ↑出発 ↑到着       ↑出発 ↑到着       ↑出発 ↑到着
ゾーン    AAAAAAA       BBBBBBBBBBB       CCCCCCCCC       AAAAAAAAAAAAA
          (自宅A)  ─    (職場B)     ─    (商業C)   ─    (自宅A)
                移動中                移動中            移動中
                (カウント外)          (カウント外)      (カウント外)

スナップショット（毎正時）での在ゾーン:
  6:00 (360分) → A（自宅）: 360 < 480 のため在宅
  8:00 (480分) → なし    : 出発時刻=480、到着=510 のため移動中
  9:00 (540分) → B（職場）: 510 ≤ 540 < 720 のため在職場
 12:00 (720分) → なし    : 出発時刻=720、到着=760 のため移動中
 13:00 (780分) → C（商業）: 760 ≤ 780 < 810 のため在商業施設
 15:00 (900分) → A（自宅）: 870 ≤ 900 < 1440 のため在宅
```

#### QGISで時系列アニメーション表示

1. `zone_population_weekday.parquet` または `zone_population_holiday.parquet` をレイヤに追加
2. `data/zone_population.qml` を適用（どちらも同じQMLで対応）
3. メニュー「表示」→「パネル」→「時間的制御」で Temporal Controller を開く
4. Temporal Controller の「全レイヤの範囲に合わせる」ボタンで時間範囲を自動設定
   - 平日ファイル: `2022-10-12 00:00` 〜 `2022-10-13 00:00`
   - 休日ファイル: `2022-10-16 00:00` 〜 `2022-10-17 00:00`
5. ステップを `1 時間` に設定して ▶ 再生

### od_lines.parquet（GeoParquet）

| フィールド | 内容 |
|---|---|
| `day_type` | 平日 / 休日 |
| `origin_city` / `origin_town` | 出発地コード |
| `origin_name` / `dest_name` | 出発地・目的地名 |
| `trip_count` | 生トリップ数（最大: 平日31、休日28） |
| `expanded_trips` | 拡大係数合計・推計人数（最大: 平日1,992、休日1,811） |

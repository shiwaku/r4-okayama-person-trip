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
│   ├── convert_to_csv.py      # Excel → CSV 一括変換
│   ├── geocode_zones.py       # ゾーン座標生成
│   ├── make_trips_full.py     # トリップデータ生成
│   ├── make_od_lines.py       # OD集計・GeoJSON/Parquet生成
│   └── make_zone_polygons.py  # ゾーンポリゴン生成
├── data/
│   ├── csv/                       # CSV変換出力
│   │   ├── code_*.csv             # コード表（15ファイル）
│   │   ├── 01_master_weekday.csv  # 平日マスターデータ ※gitignore
│   │   └── 02_master_holiday.csv  # 休日マスターデータ ※gitignore
│   ├── zone_coords.csv            # ゾーン座標対応表（2,029ゾーン）
│   ├── zone_coords.geojson        # 同上 GeoJSON（Point）
│   ├── zone_polygons.parquet      # ゾーンポリゴン GeoParquet（6.7MB）
│   ├── od_lines.parquet           # OD集計 GeoParquet（1.4MB）
│   ├── od_lines.qml               # 生トリップ数スタイル（QGISから参照）
│   ├── od_lines_expanded.qml      # 拡大係数適用スタイル（QGISから参照）
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

# 2. ゾーンコードに座標を付与（初回のみ・APIアクセスあり）
python scripts/geocode_zones.py

# 3. 全トリップCSV生成（1・2の完了後）
python scripts/make_trips_full.py

# 4. OD集計・GeoJSON/GeoParquet生成
python scripts/make_od_lines.py

# 5. ゾーンポリゴン生成（e-Stat自動ダウンロード・ネット接続必要）
python scripts/make_zone_polygons.py
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
| `polygon_source` | `e-stat`=KEY_CODE直接マッチ（1,392件）、`name`=町丁名マッチ（630件）、`city`=市区町村ポリゴン補完（7件） |

e-Stat 令和2年国勢調査 小地域データを使用。マッチング手順:
1. KEY_CODE 先頭8桁での直接マッチ（1,392件）
2. PT調査ゾーンコード表の町丁名と e-Stat S_NAME での名前マッチ（630件）
3. 市区町村レベルのポリゴン補完（7件）

124件（県外・都道府県単位ゾーン）はポリゴンなし（e-Stat岡山県データ対象外）。

### zone_coords.csv

| 列 | 内容 |
|---|---|
| `city_code` | 市区町村コード（5桁） |
| `town_code` | 大字・町コード（整数） |
| `pref_name` / `city_name` / `town_name` | 住所名 |
| `lat` / `lon` | 緯度・経度（国土地理院APIで取得） |

### od_lines.parquet（GeoParquet）

| フィールド | 内容 |
|---|---|
| `day_type` | 平日 / 休日 |
| `origin_city` / `origin_town` | 出発地コード |
| `origin_name` / `dest_name` | 出発地・目的地名 |
| `trip_count` | 生トリップ数（最大: 平日31、休日28） |
| `expanded_trips` | 拡大係数合計・推計人数（最大: 平日1,992、休日1,811） |

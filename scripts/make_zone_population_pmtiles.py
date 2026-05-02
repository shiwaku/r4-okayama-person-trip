import geopandas as gpd
import pandas as pd
import subprocess
from pathlib import Path

ROOT_DIR = Path(__file__).parent.parent
DATA_DIR = ROOT_DIR / "data"

GEOJSON_PATH = DATA_DIR / "zone_population_map.geojson"
PMTILES_PATH = DATA_DIR / "zone_population_map.pmtiles"


def load_and_pivot(path: Path, prefix: str) -> pd.DataFrame:
    df = pd.read_parquet(path, columns=["zone_key", "hour", "population"])
    wide = df.pivot(index="zone_key", columns="hour", values="population")
    wide = wide.round(0).fillna(0).astype("int32")
    wide.columns = [f"{prefix}{h}" for h in wide.columns]
    return wide.reset_index()


def main() -> None:
    print("Loading zone polygons...")
    zones = gpd.read_parquet(DATA_DIR / "zone_polygons.parquet")
    zones = zones.to_crs("EPSG:4326")
    zones = zones[["zone_key", "city_name", "town_name", "geometry"]]

    print("Loading weekday population...")
    wd = load_and_pivot(DATA_DIR / "zone_population_weekday.parquet", "w")
    print("Loading holiday population...")
    hd = load_and_pivot(DATA_DIR / "zone_population_holiday.parquet", "h")

    result = zones.merge(wd, on="zone_key", how="left")
    result = result.merge(hd, on="zone_key", how="left")

    pop_cols = [c for c in result.columns if len(c) >= 2 and c[0] in ("w", "h") and c[1:].isdigit()]
    result[pop_cols] = result[pop_cols].fillna(0).astype("int32")

    print(f"Writing GeoJSON ({len(result)} zones)...")
    result.to_file(GEOJSON_PATH, driver="GeoJSON")
    size_mb = GEOJSON_PATH.stat().st_size / 1e6
    print(f"  → {GEOJSON_PATH.name} ({size_mb:.1f} MB)")

    print("Running tippecanoe...")
    subprocess.run(
        [
            "tippecanoe",
            "-o", str(PMTILES_PATH),
            "--layer=zones",
            "--minimum-zoom=7",
            "--maximum-zoom=13",
            "--no-tile-size-limit",
            "--no-feature-limit",
            "--force",
            "--quiet",
            str(GEOJSON_PATH),
        ],
        check=True,
    )
    size_mb = PMTILES_PATH.stat().st_size / 1e6
    print(f"  → {PMTILES_PATH.name} ({size_mb:.1f} MB)")
    print("Done.")


if __name__ == "__main__":
    main()

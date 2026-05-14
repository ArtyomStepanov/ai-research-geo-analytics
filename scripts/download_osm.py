"""Download OSM amenities for a given place and save as CSV + GeoJSON.

Usage:
    python scripts/download_osm.py --city "Yerevan, Armenia" \
        --categories cafe restaurant pharmacy bar
"""
from __future__ import annotations

import argparse
from pathlib import Path

import osmnx as ox

DEFAULT_CATEGORIES = ["cafe", "restaurant", "pharmacy", "bar"]
RAW_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"


def download(city: str, categories: list[str], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    tags = {"amenity": categories}
    print(f"Fetching {categories} for '{city}' ...")
    gdf = ox.features_from_place(city, tags=tags)

    keep_cols = [c for c in ["name", "amenity", "geometry"] if c in gdf.columns]
    gdf = gdf[keep_cols].copy()
    gdf = gdf[gdf.geometry.notna()]
    gdf["lon"] = gdf.geometry.centroid.x
    gdf["lat"] = gdf.geometry.centroid.y

    slug = city.split(",")[0].strip().lower().replace(" ", "_")
    csv_path = out_dir / f"{slug}_amenities.csv"
    geo_path = out_dir / f"{slug}_amenities.geojson"

    gdf.drop(columns="geometry").to_csv(csv_path, index=False)
    gdf.to_file(geo_path, driver="GeoJSON")

    print(f"Saved {len(gdf)} rows to:\n  {csv_path}\n  {geo_path}")
    return csv_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Download OSM amenities.")
    parser.add_argument("--city", required=True, help="Place name, e.g. 'Yerevan, Armenia'")
    parser.add_argument(
        "--categories",
        nargs="+",
        default=DEFAULT_CATEGORIES,
        help="OSM amenity tags to download",
    )
    parser.add_argument("--out", default=str(RAW_DIR), help="Output directory")
    args = parser.parse_args()
    download(args.city, args.categories, Path(args.out))


if __name__ == "__main__":
    main()

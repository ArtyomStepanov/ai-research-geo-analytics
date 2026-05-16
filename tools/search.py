"""Search tools used by the agent.

Только `search_places` реализован как рабочий пример. Остальные функции —
заглушки, которые надо доработать.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from lib import datatypes
import pandas as pd

from .geo_utils import haversine_km

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def _load_places(csv_path: Optional[str] = None) -> pd.DataFrame:
    """Load amenities table.

    Порядок поиска:
        1. явный `csv_path`,
        2. `data/processed/*amenities*.csv`,
        3. `data/raw/*amenities*.csv`,
        4. `data/sample_places.csv` — встроенный safety-net датасет.
    """
    if csv_path is not None:
        return pd.read_csv(csv_path)

    for sub in ("processed", "raw"):
        for p in sorted((DATA_DIR / sub).glob("*amenities*.csv")):
            return pd.read_csv(p)

    sample = DATA_DIR / "sample_places.csv"
    if sample.exists():
        return pd.read_csv(sample)

    raise FileNotFoundError(
        "No places CSV found. Run `python scripts/download_osm.py --city ...` "
        "or `python scripts/generate_sample_data.py`."
    )


def search_places(
    category: Optional[str] = None,
    near: Optional[tuple[float, float]] = None,
    max_distance_km: Optional[float] = None,
    limit: int = 20,
    csv_path: Optional[str] = None,
) -> list[datatypes.Place]:
    """Return amenities matching the filters, optionally sorted by distance.

    Args:
        category: e.g. "cafe", "pharmacy". None = any.
        near: (lat, lon) anchor point for distance filtering/sorting.
        max_distance_km: keep only places within this radius from `near`.
        limit: max number of results.
    """
    df = _load_places(csv_path)

    if category is not None and "amenity" in df.columns:
        df = df[df["amenity"] == category]

    if near is not None and {"lat", "lon"}.issubset(df.columns):
        lat0, lon0 = near
        df = df.assign(
            distance_km=df.apply(
                lambda r: haversine_km(lat0, lon0, r["lat"], r["lon"]), axis=1
            )
        )
        if max_distance_km is not None:
            df = df[df["distance_km"] <= max_distance_km]
        df = df.sort_values("distance_km")

    result: list[datatypes.Place] = []

    for row in df.head(limit).itertuples(index=False):
        result.append(datatypes.Place(
                name=row["name"],
                amenity=row["ame"],
                distance_km=row["distance_km"],
                lat=row["lat"],
                lon=row["lon"]
            ))

    return df.head(limit).to_dict(orient="records")


def nearest_places(
    point: tuple[float, float],
    category: Optional[str] = None,
    limit: int = 5,
) -> list[datatypes.Place]:
    """Return the N nearest places to `point`."""
    return search_places(category=category, near=point, limit=limit)

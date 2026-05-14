"""Coverage / underserved-area analysis.

Сетка по lat/lon, считаем плотность целевой категории в каждой ячейке
и сравниваем с общей плотностью POI. Возвращаем ячейки с самым большим
"дефицитом" — это и есть golden-path сценарий "low pharmacy coverage".
"""
from __future__ import annotations

from typing import Optional

import pandas as pd

from .search import _load_places


def find_underserved_areas(
    category: str = "pharmacy",
    grid_size_deg: float = 0.006,
    top_k: int = 10,
    csv_path: Optional[str] = None,
) -> list[dict]:
    """Return grid cells where `category` is underrepresented relative to total activity.

    Definition (простая, baseline):
        underserved_score = total_places_in_cell - k * target_places_in_cell
    где k=3, чтобы ячейка с total=10, target=0 была сильно выше, чем с total=10, target=3.
    """
    df = _load_places(csv_path)
    if not {"lat", "lon", "amenity"}.issubset(df.columns):
        raise ValueError("Dataset must contain 'lat', 'lon', 'amenity' columns")

    df = df.copy()
    df["cell_lat"] = (df["lat"] / grid_size_deg).round().astype(int) * grid_size_deg
    df["cell_lon"] = (df["lon"] / grid_size_deg).round().astype(int) * grid_size_deg
    df["cell_lat"] = df["cell_lat"].round(6)
    df["cell_lon"] = df["cell_lon"].round(6)

    total = (
        df.groupby(["cell_lat", "cell_lon"]).size().reset_index(name="total_places")
    )
    target = (
        df[df["amenity"] == category]
        .groupby(["cell_lat", "cell_lon"])
        .size()
        .reset_index(name=f"{category}_count")
    )

    merged = total.merge(target, on=["cell_lat", "cell_lon"], how="left").fillna(0)
    merged[f"{category}_count"] = merged[f"{category}_count"].astype(int)
    merged["underserved_score"] = (
        merged["total_places"] - 3 * merged[f"{category}_count"]
    )

    merged = merged[merged["total_places"] >= 5]
    merged = merged.sort_values("underserved_score", ascending=False).head(top_k)
    return merged.to_dict(orient="records")

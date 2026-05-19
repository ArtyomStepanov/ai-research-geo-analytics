"""Hex-grid opportunity analysis for B2B site selection."""
from __future__ import annotations
from typing import Optional
import pandas as pd
import h3
from .search import _load_places

# Справочник для UI/логов: resolution -> примерный размер
HEX_SIZE_REFERENCE = {
    7: "~1.2 км ребро / ~1.6 км² площадь",
    8: "~0.74 км ребро / ~0.46 км² площадь",
    9: "~0.46 км ребро / ~0.11 км² площадь",
    10: "~0.29 км ребро / ~0.03 км² площадь",
}


def compute_opportunity_grid(
    category: str = "pharmacy",
    hex_resolution: int = 8,
    csv_path: Optional[str] = None,
    demand_threshold: float = 0.0,
    competitor_rating_weight: float = 1.0,
) -> list[dict]:
    """Рассчитать гексагональную сетку спроса и конкуренции.

    Args:
        category: Тип бизнеса для анализа (используется как фильтр конкурентов).
        hex_resolution: H3 resolution (0-15). 8 ~ городской квартал (0.74 км ребро).
        csv_path: Путь к датасету POI.
        demand_threshold: Порог видимости. Ячейки с demand_score < threshold будут прозрачными.
        competitor_rating_weight: Множитель влияния рейтинга конкурентов на насыщение.

    Returns:
        Список диктов: hex_id, center_lat/lon, boundary, demand_score, 
        competitor_density, total_places, is_visible
    """
    df = _load_places(csv_path)
    if not {"lat", "lon", "amenity"}.issubset(df.columns):
        raise ValueError("Dataset must contain 'lat', 'lon', 'amenity' columns")

    # Привязка точек к H3-гексам
    df["hex_id"] = df.apply(lambda r: h3.latlng_to_cell(r["lat"], r["lon"], hex_resolution), axis=1)

    # Агрегация: общее кол-во POI + специфика по категории
    total_agg = df.groupby("hex_id").agg(
        total_places=("lat", "count"),
        avg_rating_all=("rating", "mean"),
    ).reset_index()

    # Агрегация только по конкурентам целевой категории
    comp_df = df[df["amenity"] == category].groupby("hex_id").agg(
        competitor_count=("lat", "count"),
        competitor_weighted_rating=("rating", "sum"),
    ).reset_index()

    # Генерация полной сетки по bounding box всех POI
    margin = 0.02  # ~2 км отступ по краям
    bbox_poly = h3.LatLngPoly([
        (df["lat"].min() - margin, df["lon"].min() - margin),
        (df["lat"].max() + margin, df["lon"].min() - margin),
        (df["lat"].max() + margin, df["lon"].max() + margin),
        (df["lat"].min() - margin, df["lon"].max() + margin),
    ])
    full_grid = pd.DataFrame({"hex_id": list(h3.polygon_to_cells(bbox_poly, hex_resolution))})

    # Слияние полной сетки с агрегацией (пустые гексы получают 0)
    agg = full_grid.merge(total_agg, on="hex_id", how="left")
    agg = agg.merge(comp_df, on="hex_id", how="left")
    agg["total_places"] = agg["total_places"].fillna(0).astype(int)
    agg["competitor_count"] = agg["competitor_count"].fillna(0).astype(int)
    agg["competitor_weighted_rating"] = agg["competitor_weighted_rating"].fillna(0.0)
    agg["avg_rating_all"] = agg["avg_rating_all"].fillna(0.0)

    # Расчёт метрик TODO: улучшить
    agg["competitor_density"] = agg["competitor_weighted_rating"] * competitor_rating_weight
    agg["demand_score"] = agg["total_places"] - agg["competitor_density"]

    # Классификация видимости: demand_score выше порога (пустые гексы всегда прозрачны)
    agg["is_visible"] = agg["demand_score"] >= demand_threshold

    # Пространственный фильтр: убираем изолированные прозрачные гексы
    visible_hexes = set(agg[agg["is_visible"]]["hex_id"])
    if not visible_hexes:
        return []

    # Собираем все соседей видимых ячеек (1-hop ring)
    border_hexes = set()
    for h in visible_hexes:
        try:
            border_hexes.update(h3.grid_ring(h, 1))
        except Exception:
            pass

    # Оставляем: видимые или прозрачные, но граничащие с видимыми
    valid_hexes = visible_hexes | (set(agg["hex_id"]) & border_hexes)
    agg = agg[agg["hex_id"].isin(valid_hexes)]

    # Сборка результата для UI
    results = []
    for _, row in agg.iterrows():
        h = row["hex_id"]
        lat, lon = h3.cell_to_latlng(h)
        boundary = h3.cell_to_boundary(h)

        results.append({
            "hex_id": h,
            "center_lat": lat,
            "center_lon": lon,
            "boundary": boundary,
            "demand_score": round(float(row["demand_score"]), 2),
            "competitor_density": round(float(row["competitor_density"]), 2),
            "total_places": int(row["total_places"]),
            "is_visible": bool(row["is_visible"]),
        })

    return results

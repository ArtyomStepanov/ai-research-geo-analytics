"""Hex-grid opportunity analysis for B2B site selection."""
from __future__ import annotations

import pandas as pd
import h3
from .search import _load_places
from lib.data_types import Hex

# Центр города — начало координатной системы гексов (row=0, col=0)
CITY_CENTER = (56.8386, 60.6055)  # Екатеринбург

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
    csv_path: str | None = None,
    demand_threshold: float = 0.0,
    competitor_rating_weight: float = 0.5,
) -> list[dict]:
    """Рассчитать гексагональную сетку спроса и конкуренции.

    Метрики (на гекс):
        total_places          : общее число POI в гексе (трафик/жизнь района)
        competitor_count      : число конкурентов целевой категории
        competitor_density    : competitor_count, скорректированное на средний рейтинг
                                (высокий рейтинг конкурентов = они сильнее)
        demand_score          : total_places - competitor_count
                                (POI кроме самих конкурентов = «прокси спроса»)
        opportunity_score     : demand_score - competitor_density
                                (главная метрика: высокая = хорошее место под новую точку)
        is_visible            : True, если в гексе вообще есть POI и opportunity выше порога

    Args:
        category: Тип бизнеса для анализа (фильтр конкурентов).
        hex_resolution: H3 resolution (0-15). 8 ~ городской квартал (0.74 км ребро).
        csv_path: Путь к датасету POI.
        demand_threshold: Минимальный opportunity_score для is_visible=True.
        competitor_rating_weight: Множитель влияния рейтинга на competitor_density.
            0.0 = качество конкурентов игнорируется, считается только их число.
            0.5 = умеренный учёт (рекомендуется).

    Returns:
        Список диктов: hex_id, center_lat/lon, boundary, demand_score,
        competitor_density, competitor_count, opportunity_score,
        total_places, is_visible.
    """
    df = _load_places(csv_path)

    # Привязка точек к H3-гексам
    df["hex_id"] = df.apply(
        lambda r: h3.latlng_to_cell(r["lat"], r["lon"], hex_resolution), axis=1
    )

    # Агрегация: общее количество POI в гексе
    total_agg = df.groupby("hex_id").agg(
        total_places=("lat", "count"),
    ).reset_index()

    # Агрегация только по конкурентам целевой категории
    comp_df = df[df["amenity"] == category]
    if not comp_df.empty:
        comp_agg = comp_df.groupby("hex_id").agg(
            competitor_count=("lat", "count"),
            competitor_avg_rating=("rating", "mean"),
        ).reset_index()
    else:
        comp_agg = pd.DataFrame(
            columns=["hex_id", "competitor_count", "competitor_avg_rating"]
        )

    # Генерация полной сетки по bounding box всех POI
    margin = 0.02  # ~2 км отступ по краям
    bbox_poly = h3.LatLngPoly([
        (df["lat"].min() - margin, df["lon"].min() - margin),
        (df["lat"].max() + margin, df["lon"].min() - margin),
        (df["lat"].max() + margin, df["lon"].max() + margin),
        (df["lat"].min() - margin, df["lon"].max() + margin),
    ])
    full_grid = pd.DataFrame(
        {"hex_id": list(h3.polygon_to_cells(bbox_poly, hex_resolution))}
    )

    # Слияние полной сетки с агрегацией (пустые гексы получают 0)
    agg = full_grid.merge(total_agg, on="hex_id", how="left")
    agg = agg.merge(comp_agg, on="hex_id", how="left")
    agg["total_places"] = agg["total_places"].fillna(0).astype(int)
    agg["competitor_count"] = agg["competitor_count"].fillna(0).astype(int)
    # Если рейтинга нет (нет конкурентов или у них пусто) — берём нейтральные 3.0,
    # чтобы корректировка качества не давала ложного бонуса/штрафа.
    agg["competitor_avg_rating"] = agg["competitor_avg_rating"].fillna(3.0)

    # --- Метрики --------------------------------------------------------
    # Конкуренция: количество + корректировка на качество.
    # Если средний рейтинг конкурентов > 3 → они сильнее → density выше.
    # Если < 3 → слабее → density ниже. Шкала: 0.5 × (rating - 3) × count.
    agg["competitor_density"] = (
        agg["competitor_count"]
        + competitor_rating_weight
        * (agg["competitor_avg_rating"] - 3.0)
        * agg["competitor_count"]
    )

    # Спрос: общая активность района МИНУС сами конкуренты
    # (они уже учтены в competitor_density, не считаем их дважды).
    agg["demand_score"] = (agg["total_places"] - agg["competitor_count"]).clip(lower=0)

    # Главная метрика: возможность открыть новую точку
    agg["opportunity_score"] = agg["demand_score"] - agg["competitor_density"]

    # Видимость: только гексы, где есть POI И opportunity_score >= threshold
    agg["is_visible"] = (
        (agg["total_places"] > 0) & (agg["opportunity_score"] >= demand_threshold)
    )

    # Пространственный фильтр: убираем изолированные пустые гексы,
    # оставляем видимые + их 1-hop соседей для контекста
    visible_hexes = set(agg[agg["is_visible"]]["hex_id"])
    if not visible_hexes:
        return []

    border_hexes = set()
    for h in visible_hexes:
        try:
            border_hexes.update(h3.grid_ring(h, 1))
        except Exception:
            pass

    valid_hexes = visible_hexes | (set(agg["hex_id"]) & border_hexes)
    agg = agg[agg["hex_id"].isin(valid_hexes)]

    # Опорный гекс для системы координат (row, col)
    # row = East-West offset (positive = East), col = North-South offset (positive = South)
    # Формула: row = oi - i,  col = j - oj,  где (oi, oj) — IJ центра города
    origin_hex = h3.latlng_to_cell(CITY_CENTER[0], CITY_CENTER[1], hex_resolution)
    origin_ij = h3.cell_to_local_ij(origin_hex, origin_hex)

    # Сборка результата для UI
    results = []
    for _, row in agg.iterrows():
        h = row["hex_id"]
        lat, lon = h3.cell_to_latlng(h)
        boundary = h3.cell_to_boundary(h)

        try:
            hij = h3.cell_to_local_ij(origin_hex, h)
            grid_row = origin_ij[0] - hij[0]
            grid_col = hij[1] - origin_ij[1]
        except Exception:
            grid_row = grid_col = None

        results.append(Hex(
            hex_id=h,
            center_lat=lat,
            center_lon=lon,
            boundary=boundary,
            row=grid_row,
            col=grid_col,
            demand_score=round(float(row["demand_score"]), 2),
            competitor_density=round(float(row["competitor_density"]), 2),
            competitor_count=int(row["competitor_count"]),
            competitor_avg_rating=round(float(row["competitor_avg_rating"]), 2),
            opportunity_score=round(float(row["opportunity_score"]), 2),
            total_places=int(row["total_places"]),
            is_visible=bool(row["is_visible"]),
        ))

    return results

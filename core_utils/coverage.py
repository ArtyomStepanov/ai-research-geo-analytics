"""Hex-grid opportunity analysis for B2B site selection.

Поддерживает две стратегии (параметр `strategy`):
  - "implant"   : подсаживаем гипотетическое заведение в центр гекса,
                  считаем для него scoreR Хаффа против всех конкурентов.
                  Отвечает на вопрос "где открыть новое заведение".
  - "aggregate" : размазываем scoreR существующих заведений на гексы с
                  экспоненциальным весом. Отвечает на вопрос "где
                  сосредоточены сильные заведения".

Обе метрики выражаются в "ожидаемых людях" -> сравнимы между собой.
"""
from __future__ import annotations

import h3
import numpy as np
import pandas as pd

from core_utils.geo_utils import haversine_km_matrix
from core_utils.ranking import (
    amenity_similarity_vector,
    attractiveness,
    bayesian_rating,
    huff_scores_all_places,
    price_similarity_vector,
)
from core_utils.search import _load_demand, _load_places
from lib.data_types import Hex


HEX_SIZE_REFERENCE = {
    7: "~1.2 км ребро / ~1.6 км² площадь",
    8: "~0.74 км ребро / ~0.46 км² площадь",
    9: "~0.46 км ребро / ~0.11 км² площадь",
    10: "~0.29 км ребро / ~0.03 км² площадь",
}


# Сетка

def _build_full_grid(
    places_df: pd.DataFrame,
    hex_resolution: int,
    margin_deg: float = 0.02,
) -> list[str]:
    """Гексы, покрывающие bbox всех POI с небольшим отступом."""
    bbox_poly = h3.LatLngPoly([
        (places_df["lat"].min() - margin_deg, places_df["lon"].min() - margin_deg),
        (places_df["lat"].max() + margin_deg, places_df["lon"].min() - margin_deg),
        (places_df["lat"].max() + margin_deg, places_df["lon"].max() + margin_deg),
        (places_df["lat"].min() - margin_deg, places_df["lon"].max() + margin_deg),
    ])
    return list(h3.polygon_to_cells(bbox_poly, hex_resolution))


# Стратегия "implant": подсадка нового заведения

def _implant_scores(
    hex_centers: np.ndarray,         # (H_hex, 2): lat, lon
    places_df: pd.DataFrame,
    houses_df: pd.DataFrame,
    target_amenity: str,
    target_avg_bill: float,
    d0_m: float,
    beta: float,
    scale_log: float,
    outside_option: float,
    radius_cutoff_m: float,
    target_rating: float = 4.4,
    target_reviews: int = 5,
    chunk_size: int = 500,
) -> np.ndarray:
    """Для каждого гекса считает scoreR гипотетического заведения в его центре."""
    # Базовое предвычисление: матрица дом -> существующее заведение, decay,
    # эффективные привлекательности конкурентов с т.з. target-категории.
    sim_a = amenity_similarity_vector(target_amenity, places_df["amenity"].values)
    sim_p = price_similarity_vector(
        target_avg_bill, places_df["avg_bill"].values, scale_log=scale_log,
    )
    r_adj = bayesian_rating(
        places_df["rating"].values, places_df["reviews_count"].values,
    )
    A_competitors = attractiveness(r_adj, beta=beta) * sim_a * sim_p  # (V,)

    d_hv_m = haversine_km_matrix(
        houses_df["lat"].values[:, None], houses_df["lon"].values[:, None],
        places_df["lat"].values[None, :], places_df["lon"].values[None, :],
    )  # (H_house, V)
    pull_competitors = A_competitors[None, :] * np.exp(-d_hv_m / d0_m)  # (H_house, V)
    sum_pull_competitors = pull_competitors.sum(axis=1)  # (H_house,)

    # Привлекательность гипотетического — у него sim_a = sim_p = 1
    r_new_adj = bayesian_rating(
        np.array([target_rating]), np.array([target_reviews]),
    )[0]
    A_new = float(attractiveness(np.array([r_new_adj]), beta=beta)[0])

    pop = houses_df["count_people"].values.astype(np.float64)
    H_hex = len(hex_centers)
    scores = np.zeros(H_hex, dtype=np.float64)

    # Чанкуем по гексам, чтобы матрица (H_house, chunk) влезала в память.
    # При 50k домов и chunk=500 это ~200 МБ float64 — комфортно.
    for start in range(0, H_hex, chunk_size):
        end = min(start + chunk_size, H_hex)
        centers_chunk = hex_centers[start:end]  # (C, 2)

        d_hh_m = haversine_km_matrix(
            houses_df["lat"].values[:, None], houses_df["lon"].values[:, None],
            centers_chunk[:, 0][None, :], centers_chunk[:, 1][None, :],
        )  # (H_house, C)

        pull_new = A_new * np.exp(-d_hh_m / d0_m)  # (H_house, C)
        denom = sum_pull_competitors[:, None] + pull_new + outside_option
        prob_new = pull_new / denom

        mask = d_hh_m <= radius_cutoff_m
        contributions = pop[:, None] * prob_new * mask  # (H_house, C)
        scores[start:end] = contributions.sum(axis=0)

    return scores


# Стратегия "aggregate": размазывание scoreR существующих

def _aggregate_scores(
    hex_centers: np.ndarray,
    places_df: pd.DataFrame,
    venue_scores: np.ndarray,
    d_w_m: float,
) -> np.ndarray:
    """Сумма scoreR заведений с экспоненциальным затуханием от центра гекса."""
    d_m = haversine_km_matrix(
        hex_centers[:, 0][:, None], hex_centers[:, 1][:, None],
        places_df["lat"].values[None, :], places_df["lon"].values[None, :],
    )  # (H_hex, V)
    weights = np.exp(-d_m / d_w_m)
    return (weights * venue_scores[None, :]).sum(axis=1)


# Сглаживание оценок по сетке H3

def _smooth_hex_scores(scores: np.ndarray, hex_ids: list[str]) -> np.ndarray:
    """Усреднение оценки гекса по диску k=1 (центр + 6 соседей).

    Устраняет резкие переходы «красный рядом с зелёным»: максимальная
    разница между соседними гексами ограничена ~1/7 диапазона.
    """
    hex_to_idx = {h: i for i, h in enumerate(hex_ids)}
    smoothed = np.empty_like(scores)
    for i, h in enumerate(hex_ids):
        neighbors = [hex_to_idx[n] for n in h3.grid_disk(h, 1) if n in hex_to_idx]
        smoothed[i] = scores[neighbors].mean()
    return smoothed


# Главная функция

def compute_opportunity_grid(
    category: str = "pharmacy",
    hex_resolution: int = 9,
    strategy: str = "implant",            # "implant" | "aggregate"
    # Параметры Хаффа
    d0_m: float = 500.0,
    beta: float = 3.0,
    scale_log: float = 0.5,
    outside_option: float = 0.0,
    radius_cutoff_m: float = 2000.0,
    # Параметры "implant"
    target_avg_bill: float = 800.0,
    target_rating: float = 4.4,
    target_reviews: int = 10,
    # Параметр "aggregate"
    d_w_m: float = 300.0,
    # Фильтрация результата
    visibility_threshold: float = 0.0,
    csv_path_places: str | None = None,
    csv_path_demand: str | None = None,
    city_center: tuple[float, float] = (56.8386, 60.6055),  # Екатеринбург
) -> list[Hex]:
    """Считает гекс-сетку оценки локаций.

    Возвращает список Hex со следующими полями:
        opportunity_score : основная метрика согласно strategy (в людях)
        demand_score      : суммарное население в гексе (для контекста)
        competitor_count  : число конкурентов целевой категории в гексе
        competitor_avg_rating
        total_places      : всего POI в гексе
        is_visible        : opportunity_score >= visibility_threshold

    Параметр `strategy` определяет смысл opportunity_score:
        "implant"   -> ожидаемое число клиентов нового заведения категории
                       `category` со средним чеком target_avg_bill, если
                       его открыть в центре гекса.
        "aggregate" -> взвешенная сумма scoreR существующих заведений
                       категории `category` (с похожестью по amenity/price)
                       вокруг центра гекса.
    """
    if strategy not in ("implant", "aggregate"):
        raise ValueError(f"Unknown strategy: {strategy!r}")

    places_df = _load_places(csv_path_places).reset_index(drop=True)
    houses_df = _load_demand(csv_path_demand)

    # H3-привязка POI и домов
    places_df["hex_id"] = [
        h3.latlng_to_cell(lat, lon, hex_resolution)
        for lat, lon in zip(places_df["lat"], places_df["lon"])
    ]
    houses_df = houses_df.copy()
    houses_df["hex_id"] = [
        h3.latlng_to_cell(lat, lon, hex_resolution)
        for lat, lon in zip(houses_df["lat"], houses_df["lon"])
    ]

    # Контекстные агрегаты для UI
    demand_agg = houses_df.groupby("hex_id").agg(
        demand_people=("count_people", "sum"),
    ).reset_index()
    total_agg = places_df.groupby("hex_id").agg(
        total_places=("lat", "count"),
    ).reset_index()
    comp_df = places_df[places_df["amenity"] == category]
    if not comp_df.empty:
        comp_agg = comp_df.groupby("hex_id").agg(
            competitor_count=("lat", "count"),
            competitor_avg_rating=("rating", "mean"),
        ).reset_index()
    else:
        comp_agg = pd.DataFrame(
            columns=["hex_id", "competitor_count", "competitor_avg_rating"],
        )

    # Полная сетка
    full_grid = pd.DataFrame({"hex_id": _build_full_grid(places_df, hex_resolution)})

    agg = (
        full_grid
        .merge(total_agg, on="hex_id", how="left")
        .merge(comp_agg, on="hex_id", how="left")
        .merge(demand_agg, on="hex_id", how="left")
    )
    agg["total_places"] = agg["total_places"].fillna(0).astype(int)
    agg["competitor_count"] = agg["competitor_count"].fillna(0).astype(int)
    agg["competitor_avg_rating"] = agg["competitor_avg_rating"].fillna(0.0)
    agg["demand_people"] = agg["demand_people"].fillna(0.0)

    # Центры всех гексов
    centers = np.array([h3.cell_to_latlng(h) for h in agg["hex_id"]])  # (H_hex, 2)

    # --- Основной расчёт ------------------------------------------------
    if strategy == "implant":
        opportunity = _implant_scores(
            hex_centers=centers,
            places_df=places_df,
            houses_df=houses_df,
            target_amenity=category,
            target_avg_bill=target_avg_bill,
            target_rating=target_rating,
            target_reviews=target_reviews,
            d0_m=d0_m, beta=beta, scale_log=scale_log,
            outside_option=outside_option,
            radius_cutoff_m=radius_cutoff_m,
        )
    else:  # "aggregate"
        # scoreR считаем только для заведений целевой категории
        # (для других sim_a = 0, агрегат всё равно не учтёт их).
        cat_mask = places_df["amenity"].values == category
        venue_scores = np.zeros(len(places_df), dtype=np.float64)
        if cat_mask.any():
            scores_full = huff_scores_all_places(
                places_df, houses_df,
                d0_m=d0_m, beta=beta, scale_log=scale_log,
                outside_option=outside_option,
                radius_cutoff_m=radius_cutoff_m,
            )
            venue_scores[cat_mask] = scores_full[cat_mask]

        opportunity = _aggregate_scores(
            hex_centers=centers,
            places_df=places_df,
            venue_scores=venue_scores,
            d_w_m=d_w_m,
        )

    # Сглаживание по соседним гексам: убирает резкие переходы цвета.
    opportunity = _smooth_hex_scores(opportunity, list(agg["hex_id"]))

    agg["opportunity_score"] = opportunity
    agg["demand_score"] = agg["demand_people"]

    agg["is_visible"] = (
        (agg["total_places"] > 0) & (agg["opportunity_score"] > visibility_threshold)
    )

    # Видимые + их 1-hop соседи для контекста
    visible_hexes = set(agg.loc[agg["is_visible"], "hex_id"])
    if not visible_hexes:
        return []

    border_hexes: set[str] = set()
    for h in visible_hexes:
        try:
            border_hexes.update(h3.grid_ring(h, 1))
        except Exception:
            pass
    valid = visible_hexes | (set(agg["hex_id"]) & border_hexes)
    agg = agg[agg["hex_id"].isin(valid)].reset_index(drop=True)

    # Координатная сетка относительно центра города
    origin_hex = h3.latlng_to_cell(city_center[0], city_center[1], hex_resolution)
    origin_ij = h3.cell_to_local_ij(origin_hex, origin_hex)

    results: list[Hex] = []
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

        demand_people = float(row["demand_score"])
        comp_count = int(row["competitor_count"])
        results.append(Hex(
            hex_id=h,
            center_lat=lat,
            center_lon=lon,
            boundary=boundary,
            row=grid_row,
            col=grid_col,
            demand_score=round(demand_people, 2),
            competitor_count=comp_count,
            competitor_density=round(comp_count / max(demand_people, 1e-6), 6),
            competitor_avg_rating=round(float(row["competitor_avg_rating"]), 2),
            opportunity_score=round(float(row["opportunity_score"]), 2),
            total_places=int(row["total_places"]),
            is_visible=bool(row["is_visible"]),
        ))

    return results

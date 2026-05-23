"""Ranking strategies based on the Huff gravity model.

Также экспортирует общие функции (amenity_similarity, price_similarity,
bayesian_rating, attractiveness), которые использует coverage.py.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from core_utils.geo_utils import haversine_km_matrix
from core_utils.search import _load_places, _load_demand
from lib.data_types import Place


# Группы родственных категорий OSM. sim в [0, 1].
AMENITY_GROUPS: dict[str, dict[str, float]] = {
    "cafe":       {"cafe": 1.0, "fast_food": 0.6, "restaurant": 0.5, "bakery": 0.7},
    "restaurant": {"restaurant": 1.0, "cafe": 0.5, "fast_food": 0.4, "bar": 0.3, "pub": 0.3},
    "fast_food":  {"fast_food": 1.0, "cafe": 0.6, "restaurant": 0.4},
    "bar":        {"bar": 1.0, "pub": 0.8, "restaurant": 0.3},
    "pub":        {"pub": 1.0, "bar": 0.8, "restaurant": 0.3},
}


# Похожести

def amenity_similarity(a1: str, a2: str) -> float:
    if a1 == a2:
        return 1.0
    return AMENITY_GROUPS.get(a1, {}).get(a2, 0.0)


def price_similarity(b1, b2, sigma_log: float = 0.5) -> float:
    """Похожесть по среднему чеку (в рублях), на лог-шкале.

    sigma_log=0.5  -> разница в 1.5x даёт ~0.45, в 2x  ~0.25, в 3x ~0.11.
    NaN/неположительные -> 1.0 (нет информации = не штрафуем).
    """
    if pd.isna(b1) or pd.isna(b2):
        return 1.0
    if b1 <= 0 or b2 <= 0:
        return 1.0
    return float(np.exp(-abs(np.log(b1) - np.log(b2)) / sigma_log))


def amenity_similarity_vector(target_amenity: str, amenities: np.ndarray) -> np.ndarray:
    """Векторизованная sim_a для одного target ко всем заведениям. shape (V,)."""
    return np.array(
        [amenity_similarity(target_amenity, a) for a in amenities],
        dtype=np.float64,
    )


def price_similarity_vector(
    target_bill: float, bills: np.ndarray, sigma_log: float = 0.5,
) -> np.ndarray:
    """Векторизованная sim_p. shape (V,). Корректно обрабатывает NaN/<=0."""
    bills = np.asarray(bills, dtype=np.float64)
    valid = np.isfinite(bills) & (bills > 0) & np.isfinite(target_bill) & (target_bill > 0)
    out = np.ones_like(bills, dtype=np.float64)
    if valid.any():
        out[valid] = np.exp(
            -np.abs(np.log(bills[valid]) - np.log(target_bill)) / sigma_log
        )
    return out


# Привлекательность

def bayesian_rating(
    rating: np.ndarray, n_reviews: np.ndarray,
    global_mean: float = 4.2, m: float = 20.0,
) -> np.ndarray:
    return (n_reviews * rating + m * global_mean) / (n_reviews + m)


def attractiveness(rating_adj: np.ndarray, beta: float = 3.0) -> np.ndarray:
    return rating_adj ** beta


# Хафф для одного заведения

def huff_score_place(
    target_idx: int,
    places: pd.DataFrame,
    houses: pd.DataFrame,
    d0_m: float = 500.0,
    beta: float = 3.0,
    sigma_log: float = 0.5,
    outside_option: float = 0.0,
    radius_cutoff_m: float = 2000.0,
) -> float:
    """scoreR для places.iloc[target_idx] по модели Хаффа.

    Параметры расстояний — в МЕТРАХ; внутренний haversine_km_matrix
    возвращает километры, поэтому умножаем на 1000 один раз.

    Ожидаемые колонки:
        places: amenity, price_level (avg_bill в рублях),
                rating, reviews_count, lat, lon
        houses: lat, lon, count_people
    """
    target = places.iloc[target_idx]

    sim_a = amenity_similarity_vector(target["amenity"], places["amenity"].values)
    sim_p = price_similarity_vector(
        target["price_level"], places["price_level"].values, sigma_log=sigma_log,
    )

    r_adj = bayesian_rating(
        places["rating"].values, places["reviews_count"].values,
    )
    A = attractiveness(r_adj, beta=beta) * sim_a * sim_p  # (V,)

    # Матрица расстояний (H, V) в метрах
    dists = 1000.0 * haversine_km_matrix(
        houses["lat"].values[:, None], houses["lon"].values[:, None],
        places["lat"].values[None, :], places["lon"].values[None, :],
    )

    keep = dists[:, target_idx] <= radius_cutoff_m
    if not keep.any():
        return 0.0

    dists_k = dists[keep]
    pop = houses["count_people"].values[keep]

    pull = A[None, :] * np.exp(-dists_k / d0_m)        # (H_keep, V)
    denom = pull.sum(axis=1) + outside_option
    prob_target = pull[:, target_idx] / denom
    return float((pop * prob_target).sum())


def huff_scores_all_places(
    places: pd.DataFrame,
    houses: pd.DataFrame,
    d0_m: float = 500.0,
    beta: float = 3.0,
    sigma_log: float = 0.5,
    outside_option: float = 0.0,
    radius_cutoff_m: float = 2000.0,
) -> np.ndarray:
    """scoreR для всех заведений сразу.

    В отличие от наивного цикла huff_score_place * V раз, тут матрица
    расстояний и базовая g(r) считаются один раз. Per-target меняются
    только sim_a, sim_p и радиусный фильтр.

    Возвращает массив длины len(places).
    """
    V = len(places)
    if V == 0:
        return np.array([], dtype=np.float64)

    amen = places["amenity"].values
    bills = places["price_level"].values.astype(np.float64)

    r_adj = bayesian_rating(
        places["rating"].values, places["reviews_count"].values,
    )
    g = attractiveness(r_adj, beta=beta)  # (V,)

    dists = 1000.0 * haversine_km_matrix(
        houses["lat"].values[:, None], houses["lon"].values[:, None],
        places["lat"].values[None, :], places["lon"].values[None, :],
    )  # (H, V)
    decay = np.exp(-dists / d0_m)  # (H, V)
    pop = houses["count_people"].values  # (H,)

    scores = np.zeros(V, dtype=np.float64)
    for j in range(V):
        sim_a = amenity_similarity_vector(amen[j], amen)
        sim_p = price_similarity_vector(bills[j], bills, sigma_log=sigma_log)
        A_eff = g * sim_a * sim_p  # (V,)

        keep = dists[:, j] <= radius_cutoff_m
        if not keep.any():
            continue

        pull = A_eff[None, :] * decay[keep]            # (H_keep, V)
        denom = pull.sum(axis=1) + outside_option
        prob_j = pull[:, j] / denom
        scores[j] = (pop[keep] * prob_j).sum()

    return scores


# Стратегии ранжирования для API

def rank_by_distance(places: Iterable[Place]) -> list[Place]:
    """Sort places by precomputed `distance_km` field (ascending)."""
    return sorted(
        places,
        key=lambda p: float("inf") if p.distance_km is None else p.distance_km,
    )


def rank_by_score(
    places: Iterable[Place],
    d0_m: float = 500.0,
    beta: float = 3.0,
    sigma_log: float = 0.5,
    outside_option: float = 0.0,
    radius_cutoff_m: float = 2000.0,
) -> list[Place]:
    """Sort by Huff score, attaching the score back to each Place."""
    places = list(places)
    if not places:
        return []

    places_df = _load_places().reset_index(drop=True)
    houses_df = _load_demand()

    # Сопоставляем каждый Place с позиционным индексом в places_df по (lat, lon).
    # Координаты приходят из того же CSV без арифметики -> float equality ок.
    lat_lon_to_idx: dict[tuple[float, float], int] = {
        (row["lat"], row["lon"]): i for i, row in places_df.iterrows()
    }

    # Подмешиваем недостающие места (например созданные вручную) один раз,
    # чтобы потом одним проходом посчитать Хафф для всех нужных индексов.
    extra_rows = []
    target_indices: list[int] = []
    for p in places:
        idx = lat_lon_to_idx.get((p.lat, p.lon))
        if idx is None:
            extra_rows.append({
                "amenity": p.amenity, "name": p.name,
                "rating": p.rating or 0.0, "reviews_count": 0,
                "price_level": p.price_level, "lat": p.lat, "lon": p.lon,
            })
            idx = len(places_df) + len(extra_rows) - 1
            lat_lon_to_idx[(p.lat, p.lon)] = idx
        target_indices.append(idx)

    if extra_rows:
        places_df = pd.concat(
            [places_df, pd.DataFrame(extra_rows)], ignore_index=True,
        )

    # Считаем один раз для всех. Если запрошено < 5% мест из датасета,
    # точечный цикл по huff_score_place был бы экономнее; для общего
    # случая глобальный вариант проще и предсказуемее по сложности.
    all_scores = huff_scores_all_places(
        places_df, houses_df,
        d0_m=d0_m, beta=beta, sigma_log=sigma_log,
        outside_option=outside_option, radius_cutoff_m=radius_cutoff_m,
    )

    for p, idx in zip(places, target_indices):
        p.score = float(all_scores[idx])

    return sorted(places, key=lambda p: p.score, reverse=True)

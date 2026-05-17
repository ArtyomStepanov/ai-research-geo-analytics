"""Ranking strategies.

Baseline `score_place` намеренно простой — это стартовая точка, а не
финальная формула. Сравнение разных стратегий — в notebooks/03.
"""
from __future__ import annotations

from lib.data_types import Place
from typing import Iterable

DEFAULT_WEIGHTS = {"rating": 0.7, "distance": 0.3}


def score_place(place: Place, weights: dict | None = None) -> float:
    """Composite score for a single place.

        score = w_rating * rating - w_distance * distance_km

    `distance_km` берётся из place['distance_km'], если не задан явно.
    """
    w = weights or DEFAULT_WEIGHTS
    rating = 0.0 if place.rating is None else place.rating
    distance_km = 0.0 if place.distance_km is None else place.distance_km
    return w["rating"] * rating - w["distance"] * distance_km


def rank_by_distance(places: Iterable[Place]) -> list[Place]:
    """Sort places by precomputed `distance_km` field (ascending)."""
    return sorted(places, key=lambda p: float("inf") if p.distance_km is None else p.distance_km)


def rank_by_score(places: Iterable[Place], weights: dict | None = None) -> list[Place]:
    """Sort by composite `score_place`, attaching the score back to each row."""
    # TODO: избавится от мутации 
    scored: list[Place] = []
    for p in places:
        p.score = score_place(p, weights=weights)
        scored.append(p)
    return sorted(scored, key=lambda p: p.score, reverse=True)

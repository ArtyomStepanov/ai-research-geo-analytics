"""Ranking strategies.

Baseline `score_place` намеренно простой — это стартовая точка, а не
финальная формула. Сравнение разных стратегий — в notebooks/03.
"""
from __future__ import annotations

from typing import Iterable

DEFAULT_WEIGHTS = {"rating": 0.7, "distance": 0.3}


def score_place(place: dict, distance_km: float | None = None, weights: dict | None = None) -> float:
    """Composite score for a single place.

        score = w_rating * rating - w_distance * distance_km

    `distance_km` берётся из place['distance_km'], если не задан явно.
    """
    w = weights or DEFAULT_WEIGHTS
    rating = float(place.get("rating", 0.0) or 0.0)
    if distance_km is None:
        distance_km = float(place.get("distance_km", 0.0) or 0.0)
    return w["rating"] * rating - w["distance"] * distance_km


def rank_by_distance(places: Iterable[dict]) -> list[dict]:
    """Sort places by precomputed `distance_km` field (ascending)."""
    return sorted(places, key=lambda p: p.get("distance_km", float("inf")))


def rank_by_score(places: Iterable[dict], weights: dict | None = None) -> list[dict]:
    """Sort by composite `score_place`, attaching the score back to each row."""
    scored = []
    for p in places:
        s = score_place(p, weights=weights)
        scored.append({**p, "score": round(s, 4)})
    return sorted(scored, key=lambda p: p["score"], reverse=True)

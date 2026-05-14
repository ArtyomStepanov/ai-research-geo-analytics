"""Filtering helpers — skeleton."""
from __future__ import annotations

from typing import Iterable


def filter_by_category(places: Iterable[dict], category: str) -> list[dict]:
    return [p for p in places if p.get("amenity") == category]


def filter_by_rating(places: Iterable[dict], min_rating: float) -> list[dict]:
    """TODO: рейтингов в OSM нет — выбрать источник (Yelp, Google, синтетика)."""
    return [p for p in places if p.get("rating", 0) >= min_rating]

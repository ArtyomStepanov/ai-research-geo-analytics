from __future__ import annotations

from pydantic import BaseModel


class Place(BaseModel):
    name: str | None = None
    amenity: str | None = None
    distance_km: float | None = None
    rating: float | None = None
    avg_bill: float | None = None
    score: float | None = None
    lat: float
    lon: float

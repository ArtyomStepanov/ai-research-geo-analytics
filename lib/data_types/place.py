from pydantic import BaseModel

class Place(BaseModel):
    name: str | None = None
    amenity: str | None = None
    distance_km: float | None = None
    rating: float | None = None
    price_level: str | None = None
    score: float | None = None
    opening_hours: str | None = None
    lat: float
    lon: float

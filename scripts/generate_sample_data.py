"""Generate a deterministic sample dataset for the project.

Это safety net на случай, когда Overpass / osmnx недоступны.
Записывает CSV с ~700 синтетическими POI вокруг Еревана.

Запуск:
    python scripts/generate_sample_data.py
"""
from __future__ import annotations

import csv
import math
import random
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "data" / "sample_places.csv"

# Yerevan-ish center
CENTER = (40.1772, 44.5152)

# Несколько кластеров с разной плотностью разных категорий.
# Это даёт нетривиальный паттерн "underserved areas" для демо.
NEIGHBORHOODS = [
    # name, lat, lon, mix per amenity (cafe, restaurant, pharmacy, bar)
    ("Center",      40.1810, 44.5140, dict(cafe=120, restaurant=120, pharmacy=15, bar=40)),
    ("Arabkir",     40.2050, 44.5210, dict(cafe=50,  restaurant=40,  pharmacy=25, bar=10)),
    ("Kentron-S",   40.1690, 44.5090, dict(cafe=40,  restaurant=50,  pharmacy=10, bar=20)),
    ("Davtashen",   40.2180, 44.4720, dict(cafe=10,  restaurant=15,  pharmacy=4,  bar=2)),
    ("Erebuni",     40.1450, 44.5350, dict(cafe=15,  restaurant=20,  pharmacy=6,  bar=3)),
    ("Malatia",     40.1620, 44.4670, dict(cafe=20,  restaurant=25,  pharmacy=12, bar=5)),
    ("Nor-Nork",    40.1950, 44.5650, dict(cafe=25,  restaurant=25,  pharmacy=8,  bar=4)),
]

CAFE_NAMES = ["Kupatak", "Lumen", "Coffeeshop Co", "Green Bean", "Achajour",
              "Caffeine Lab", "Aperto", "Sketch", "The Espresso", "Sip"]
RESTAURANT_NAMES = ["Tavern", "Anteb", "Gata House", "Lavash", "Sherep",
                    "Caucasus", "Wine Republic", "Dolmama", "Aregak", "Karas"]
PHARMACY_NAMES = ["Natali Pharm", "Alfa-Farm", "Pharm Express", "Aibolit",
                  "Med Pharm", "Plus Pharm", "Health+", "City Pharm"]
BAR_NAMES = ["12 Tables", "Calumet", "Stop Club", "Beatles Pub", "Tap",
             "Republic", "The Loft", "Liberty Bar"]

NAME_POOL = {
    "cafe": CAFE_NAMES,
    "restaurant": RESTAURANT_NAMES,
    "pharmacy": PHARMACY_NAMES,
    "bar": BAR_NAMES,
}


def jitter(center_lat: float, center_lon: float, sigma_deg: float, rng: random.Random):
    # Box-Muller для симуляции нормального распределения
    u1, u2 = rng.random(), rng.random()
    r = math.sqrt(-2.0 * math.log(max(u1, 1e-9)))
    theta = 2.0 * math.pi * u2
    dlat = sigma_deg * r * math.cos(theta)
    dlon = sigma_deg * r * math.sin(theta) / math.cos(math.radians(center_lat))
    return center_lat + dlat, center_lon + dlon


def main() -> None:
    rng = random.Random(42)
    OUT.parent.mkdir(parents=True, exist_ok=True)

    rows = []
    place_id = 0
    for name, lat0, lon0, mix in NEIGHBORHOODS:
        for amenity, n in mix.items():
            pool = NAME_POOL[amenity]
            for _ in range(n):
                lat, lon = jitter(lat0, lon0, sigma_deg=0.006, rng=rng)
                # Rating: cafe/restaurant/bar 3.5-5.0; pharmacy 3.0-4.5
                if amenity == "pharmacy":
                    rating = round(rng.uniform(3.0, 4.5), 1)
                else:
                    rating = round(rng.uniform(3.5, 5.0), 1)
                rows.append(
                    {
                        "id": place_id,
                        "name": f"{rng.choice(pool)} #{place_id % 90 + 1}",
                        "amenity": amenity,
                        "lat": round(lat, 6),
                        "lon": round(lon, 6),
                        "rating": rating,
                        "district": name,
                    }
                )
                place_id += 1

    rng.shuffle(rows)
    fields = ["id", "name", "amenity", "lat", "lon", "rating", "district"]
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {len(rows)} rows -> {OUT}")


if __name__ == "__main__":
    main()

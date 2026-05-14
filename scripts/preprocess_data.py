"""Preprocess raw OSM data into a clean table for the agent.

TODO: нормализация имён, дедупликация, обогащение рейтингами / часами
работы, разбиение по районам.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
PROCESSED = Path(__file__).resolve().parent.parent / "data" / "processed"


def preprocess(input_csv: Path, output_csv: Path) -> None:
    df = pd.read_csv(input_csv)
    df = df.dropna(subset=["lat", "lon"])
    df["name"] = df.get("name", pd.Series([None] * len(df))).fillna("unknown")
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    print(f"Wrote {len(df)} rows -> {output_csv}")


if __name__ == "__main__":
    # TODO: argparse + поддержка нескольких городов
    raise SystemExit("Fill in preprocessing pipeline in scripts/preprocess_data.py")

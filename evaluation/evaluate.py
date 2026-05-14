"""Minimal benchmark runner.

Запуск:
    python -m evaluation.evaluate
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(ROOT))

from agent.agent import run as run_agent  # noqa: E402

QUERIES_PATH = Path(__file__).resolve().parent / "benchmark_queries.json"


def main() -> None:
    queries = json.loads(QUERIES_PATH.read_text())
    rows = []
    for q in queries:
        try:
            answer = run_agent(q)
            status = "ok" if answer else "empty"
        except Exception as exc:  # noqa: BLE001
            answer = str(exc)
            status = "error"
        rows.append({"query": q, "status": status, "answer": answer[:200]})

    print(json.dumps(rows, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

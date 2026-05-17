"""Minimal LLM agent: query -> choose tool -> execute tool -> answer.

Цикл намеренно простой: один шаг tool calling, без памяти и многошагового
планирования. Расширять отдельно (см. README, секция "How tool calling works").

Запуск:
    python -m agent.agent "Find quiet cafe near metro"
    python -m agent.agent "Find areas with low pharmacy coverage"
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any

from dotenv import load_dotenv

from core_utils.coverage import find_underserved_areas
from core_utils.search import search_places

from .tools import (
    _tool_coverage, 
    _tool_distance,
    _tool_filtering,
    _tool_rank,
    _tool_search
)

from .prompts import SYSTEM_PROMPT
from .tools_schema import TOOLS

load_dotenv()


TOOL_IMPL = {
    "search_places": _tool_search,
    "rank_places": _tool_rank,
    "find_underserved_areas": _tool_coverage,
    "filter_places": _tool_filtering,
    "compute_distance": _tool_distance,
}


def _offline_route(query: str) -> str:
    """Простая эвристика-роутинг для оффлайн-режима (без OPENAI_API_KEY).

    Это НЕ замена LLM — это safety net, чтобы pipeline можно было прогнать
    end-to-end без сети и ключа.
    """
    q = query.lower()
    if "underserved" in q or "low" in q and "coverage" in q or "lack" in q:
        cat = "pharmacy" if "pharmacy" in q else "cafe" if "cafe" in q else "pharmacy"
        cells = find_underserved_areas(category=cat, top_k=5)
        return (
            f"[offline] Top underserved cells for '{cat}':\n"
            + json.dumps(cells, indent=2, ensure_ascii=False, default=str)
        )

    category = None
    for c in ("cafe", "restaurant", "pharmacy", "bar"):
        if c in q:
            category = c
            break
    places = search_places(category=category, limit=5)
    return (
        f"[offline] First {len(places)} places (category={category}):\n"
        + json.dumps(places, indent=2, ensure_ascii=False, default=str)
    )


def _llm_client_and_model():
    """Build an OpenAI-compatible client.

    Поддерживаются три варианта:
        1. Внешний OpenAI: задан только `OPENAI_API_KEY`.
        2. Self-hosted (Ollama / vLLM / LM Studio / llama.cpp server) — задаём
           `LLM_BASE_URL` (или `OPENAI_BASE_URL`) и `LLM_MODEL`. API-ключ
           локальные серверы обычно не валидируют, можно подставить любую строку.
        3. Любой другой OpenAI-совместимый endpoint (Together, Groq, ...).
    """
    from openai import OpenAI

    base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY") or ("local" if base_url else None)
    model = f"gpt://{os.getenv("YANDEX_CLOUD_FOLDER")}/{os.getenv("YANDEX_CLOUD_MODEL", "gpt-4o-mini")}"
    return OpenAI(base_url=base_url, api_key=api_key), model


def run(query: str) -> str:
    """Run one turn of: LLM -> tool -> LLM answer.

    Если не задан ни `OPENAI_API_KEY`, ни `LLM_BASE_URL` — падает в
    оффлайн-роутинг (см. `_offline_route`).
    """
    if not (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")):
        return _offline_route(query)

    client, model = _llm_client_and_model()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query},
    ]

    first = client.chat.completions.create(model=model, messages=messages, tools=TOOLS)
    msg = first.choices[0].message
    messages.append(msg.model_dump(exclude_none=True))

    for call in msg.tool_calls or []:
        name = call.function.name
        args = json.loads(call.function.arguments or "{}")
        impl = TOOL_IMPL.get(name)
        result = impl(args) if impl else {"error": f"unknown tool {name}"}
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
            }
        )

    final = client.chat.completions.create(model=model, messages=messages)
    return final.choices[0].message.content or ""


def main() -> None:
    query = " ".join(sys.argv[1:]) or "Find areas with low pharmacy coverage"
    print(run(query))


if __name__ == "__main__":
    main()

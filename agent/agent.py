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

from dotenv import load_dotenv

from core_utils.coverage import compute_opportunity_grid
from core_utils.search import search_places

from .db import init_db, save_opportunity_grid
from .memory import PersistedMemory
from .prompts import SYSTEM_PROMPT
from .tools import (
    _tool_opportunity_grid,
    _tool_nearest_hexes,
    _tool_distance,
    _tool_filtering,
    _tool_rank,
    _tool_search_places,
    _tool_nearest_places,
    _tool_search_by_name,
    _tool_build_heatmap,
    _tool_geocode,
)
from .tools_schema import TOOLS

load_dotenv()


TOOL_IMPL = {
    "geocode": _tool_geocode,
    "nearest_places": _tool_nearest_places,
    "nearest_hexes": _tool_nearest_hexes,
    "search_by_name": _tool_search_by_name,
    "search_places": _tool_search_places,
    "rank_places": _tool_rank,
    "opportunity_grid": _tool_opportunity_grid,
    "filter_places": _tool_filtering,
    "compute_distance": _tool_distance,
    "build_heatmap": _tool_build_heatmap,
}


def _offline_route(query: str) -> str:
    """Простая эвристика-роутинг для оффлайн-режима (без OPENAI_API_KEY).

    Это НЕ замена LLM — это safety net, чтобы pipeline можно было прогнать
    end-to-end без сети и ключа.
    """
    q = query.lower()
    if "underserved" in q or "low" in q and "coverage" in q or "lack" in q or "open" in q:
        cat = "pharmacy" if "pharmacy" in q else "cafe" if "cafe" in q else "pharmacy"
        cells = compute_opportunity_grid(category=cat, hex_resolution=8)
        return (
            f"[offline] Opportunity grid for '{cat}' ({len(cells)} hexes):\n"
            + json.dumps(cells[:5], indent=2, ensure_ascii=False, default=str)
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
    model = f"gpt://{os.getenv('YANDEX_CLOUD_FOLDER')}/{os.getenv('YANDEX_CLOUD_MODEL', 'gpt-4o-mini')}"
    return OpenAI(base_url=base_url, api_key=api_key), model


def run(query: str, chat_id: str) -> str:
    """Run agent with memory and multi-step tool calling.
    Args:
        query: User query
    Returns:
        Final assistant response as string.
    """
    # Добавляем запрос пользователя в память
    init_db()  # Создаём таблицу при первом запуске

    # Используем PersistedMemory, если не передан кастомный объект
    memory = PersistedMemory(chat_id=chat_id, system_prompt=SYSTEM_PROMPT)

    memory.add_user_message(query)
    memory.save()  # Persist user message immediately

    # Оффлайн-режим (без API)
    if not (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")):
        return _offline_route(query)

    client, model = _llm_client_and_model()

    # Цикл tool calling: максимум 5 итераций, чтобы избежать бесконечного цикла
    max_iterations = 5
    for iteration in range(max_iterations):
        messages = memory.get_messages()

        response = client.chat.completions.create(
            model=model,
            messages=messages,
            tools=TOOLS,
            max_tokens=65536,
            tool_choice="auto",
            temperature=0.3,
        )
        msg = response.choices[0].message

        if not msg.tool_calls:
            memory.add_assistant_message(msg.content or "")
            memory.save()
            return msg.content or ""

        memory.add_assistant_message(msg.content, msg.tool_calls)

        for call in msg.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments or "{}")
            impl = TOOL_IMPL.get(name)

            if impl:
                result = impl(args)
            else:
                result = {"error": f"unknown tool '{name}'"}

            if name == "opportunity_grid" and isinstance(result, list):
                save_opportunity_grid(chat_id, {"cells": result, "args": dict(args)})

            # Добавляем результат инструмента в память
            memory.add_tool_result(
                call.id,
                json.dumps(result, ensure_ascii=False, default=str)
            )

        memory.save()  # Persist after each complete tool-call iteration

    # Если достигли лимита итераций — просим LLM сформулировать ответ на основе накопленного контекста
    memory.add_assistant_message(
        "[System] Please provide a final answer based on the tools executed so far."
    )
    final = client.chat.completions.create(
        model=model,
        messages=memory.get_messages()
    )
    memory.save()
    return final.choices[0].message.content or ""


def main() -> None:
    memory = PersistedMemory(SYSTEM_PROMPT)
    query = " ".join(sys.argv[1:])
    print(run(query, memory=memory))


if __name__ == "__main__":
    main()

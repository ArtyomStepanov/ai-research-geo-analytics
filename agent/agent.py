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

from core_utils.coverage import find_underserved_areas
from core_utils.search import search_places

from typing import Optional

from .memory import ConversationMemory

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
    print("DEBUG: Build client", flush=True)
    base_url = os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")
    api_key = os.getenv("OPENAI_API_KEY") or ("local" if base_url else None)
    model = model = f"gpt://{os.getenv('YANDEX_CLOUD_FOLDER')}/{os.getenv('YANDEX_CLOUD_MODEL', 'gpt-4o-mini')}"
    return OpenAI(base_url=base_url, api_key=api_key), model


def run(query: str, memory: Optional["ConversationMemory"] = ConversationMemory(SYSTEM_PROMPT)) -> str:
    """Run agent with memory and multi-step tool calling.
    
    Args:
        query: User query
        memory: Optional ConversationMemory instance for persistent context.
                If None, creates ephemeral memory for this turn only.
    
    Returns:
        Final assistant response as string.
    """
    
    # Добавляем запрос пользователя в память
    memory.add_user_message(query)
    
    # Оффлайн-режим (без API)
    if not (os.getenv("OPENAI_API_KEY") or os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL")):
        return _offline_route(query)
    
    client, model = _llm_client_and_model()
    
    # Цикл tool calling: максимум 5 итераций, чтобы избежать бесконечного цикла
    max_iterations = 5
    for iteration in range(max_iterations):
        print(f"[DEBUG] Iteration {iteration + 1}/{max_iterations}", flush=True)
        
        # Получаем актуальную историю сообщений
        messages = memory.get_messages()
        
        # Запрос к LLM
        response = client.chat.completions.create(
            model=model, 
            messages=messages, 
            tools=TOOLS
        )
        msg = response.choices[0].message
        
        # Если нет tool_calls — финальный ответ
        if not msg.tool_calls:
            memory.add_assistant_message(msg.content or "")
            return msg.content or ""
        
        # Иначе: выполняем инструменты и добавляем результаты в память
        memory.add_assistant_message(msg.content, msg.tool_calls)
        
        for call in msg.tool_calls:
            name = call.function.name
            args = json.loads(call.function.arguments or "{}")
            impl = TOOL_IMPL.get(name)
            
            if impl:
                result = impl(args)
            else:
                result = {"error": f"unknown tool '{name}'"}
                print(f"[WARN] Unknown tool: {name}", flush=True)
            
            # Добавляем результат инструмента в память
            memory.add_tool_result(
                call.id, 
                json.dumps(result, ensure_ascii=False, default=str)
            )
            print(f"[TOOL] {name} → {type(result).__name__}", flush=True)
    
    # Если достигли лимита итераций — просим LLM сформулировать ответ на основе накопленного контекста
    print("[WARN] Max iterations reached, forcing final answer", flush=True)
    memory.add_assistant_message(
        "[System] Please provide a final answer based on the tools executed so far."
    )
    final = client.chat.completions.create(
        model=model,
        messages=memory.get_messages()
    )
    return final.choices[0].message.content or ""

def main() -> None:    
    # Создаём память на всю сессию (сохраняется между запросами в рамках одного запуска)
    memory = ConversationMemory(SYSTEM_PROMPT)

    query = " ".join(sys.argv[1:])

    print(f"[QUERY] {query}", flush=True)
    print(run(query, memory=memory))


if __name__ == "__main__":
    main()

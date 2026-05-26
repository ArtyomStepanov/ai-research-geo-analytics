# Benchmark: comparison of LLM/SLM backends

## Quick start

1. Запустить Ollama и поставить нужные модели:
```bash
   ollama pull qwen2.5:14b
   ollama pull llama3.1:8b
   ollama serve
```

2. Прогнать бенчмарк на каждой модели (логи копятся в `logs/`):
```bash
   python -m evaluation.evaluate --backend ollama --model qwen2.5:14b --n-repeats 5
   python -m evaluation.evaluate --backend ollama --model llama3.1:8b --n-repeats 5
```
   Каждый прогон — это 60 запросов × 5 повторов = 300 runs.
   Время: ~30-60 мин для 7-8B моделей, ~60-90 мин для 14B на M4 24GB.

3. Получить сравнительный отчёт:
```bash
   python -m evaluation.evaluate --analyze
```
   Создаст `logs/comparison.csv` и `logs/comparison.md`.

## Что меряем

- **Strict tool-seq match** — последовательность вызванных тулов точно равна expected.
- **Soft tool-set match** — все expected тулы вызваны (порядок не важен).
- **Args subset match** — ключевые поля аргументов совпали с expected.
- **Args valid rate** — доля вызовов, где аргументы прошли валидацию Pydantic.
- **Calls per run** — сколько тулов агент вызвал. Меньше — лучше, при равной точности.
- **Latency** — total + только LLM (без тулов).
- **Tokens** — prompt/completion (если бэкенд отдаёт usage).
- **Terminated by** — `answer` / `max_iterations` / `exception` / `offline`.

## Структура логов

`logs/runs.jsonl` — одна строка на run:
```json
{"run_id": "...", "model": "qwen2.5:14b", "user_query": "...",
 "final_answer": "...", "tool_sequence": ["geocode", "nearest_places"],
 "n_tool_calls": 2, "total_latency_ms": 8420, ...}
```

`logs/tool_calls.jsonl` — одна строка на каждый tool call:
```json
{"run_id": "...", "tool_name": "geocode", "tool_arguments": {...},
 "arguments_valid": true, "result_summary": {"status": "ok", ...}, ...}
```

Связь по `run_id`.

## Бенчмарк (60 запросов)

Категории и сколько запросов в каждой:

- `geocode_then_search` (5) — geocode → nearest_places
- `opportunity_implant` (7) — opportunity_grid с implant-стратегией
- `opportunity_aggregate` (5) — opportunity_grid с aggregate-стратегией
- `name_lookup` (5) — search_by_name по бренду
- `nearby_simple` (4) — поиск с координатами
- `broad_search` (4) — все объекты категории
- `distance` (2) — compute_distance
- `geocode_only` (3) — только geocode
- `ranking` (3) — search + rank_places
- `filtering` (2) — search + filter_places
- `hex_analysis` (2) — nearest_hexes
- `complex_chain` (3) — длинные цепочки
- `category_normalization` (4) — coffee → cafe, drugstore → pharmacy, etc.
- `heatmap` (2) — build_heatmap
- `ambiguous` (3) — должно быть уточнение, expected_tools=[]
- `out_of_scope` (6) — не геозапрос или injection, expected_tools=[]

## Перед первым прогоном

1. **Проверь hex_id в q41/q42** — они должны существовать в твоей сетке.
   Запусти один раз `compute_opportunity_grid(category="pharmacy")` и
   подставь реальные id.
2. **Проверь geocoder** — попробуй вручную, что Plотинку и др. находит.
3. **Удали старые логи**, если они есть: `rm logs/*.jsonl` — иначе анализ
   смешает старые и новые прогоны.
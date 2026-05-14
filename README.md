# Geo AI Assistant

Исследовательская geo-AI система: интерактивный анализ городской среды через естественно-языковые запросы поверх OpenStreetMap-данных.

> **Цель проекта — не "сделать AI-агента", а построить исследовательскую geo-AI систему.**
> LLM-агент — это интерфейс. Содержательная работа лежит в данных, метриках, ранжировании и в том, какие исследовательские выводы получаются на выходе.

## Описание

Проект посвящён пространственному анализу городской инфраструктуры и моделированию пользовательских сценариев на основе открытых геоданных, в первую очередь OpenStreetMap. Команда фокусируется на сборе, очистке и разведочном анализе информации: оценке плотности распределения объектов, расчёте дистанций и определении доступности различных сервисов. Обработанные данные становятся базой для алгоритмов поиска и ранжирования, способных выявлять неочевидные паттерны — например, находить районы с локальным дефицитом конкретных услуг.

Результат — интерактивная аналитическая система с умным ассистентом, позволяющая исследовать городскую среду с помощью сложных естественных запросов. Основной акцент сделан на визуализации геоданных (тепловые карты, гео-дашборды) и формировании исследовательских выводов о том, как полнота исходной информации и выбранные математические метрики влияют на итоговое качество рекомендаций.

Внутри используются:

- **OpenStreetMap** (через `osmnx`) — источник геоданных
- **Retrieval / Ranking** — алгоритмы поиска и ранжирования объектов
- **LLM Assistant** — оркестрация tool calling поверх естественно-языковых запросов
- **Visualization** — `folium`, `streamlit` для интерактивных карт и дашбордов

## Архитектура

```text
User Query
    ↓
LLM Assistant   (chooses a tool based on the query)
    ↓
Tool Calling    (search / rank / coverage analysis)
    ↓
Geo Retrieval / Ranking   (over OSM-derived dataset)
    ↓
Visualization + Response  (folium map + LLM summary)
```

## How tool calling works

Один шаг агента — это явный цикл:

1. **Query** — пользователь задаёт вопрос на естественном языке.
2. **Tool selection** — LLM (через OpenAI tool calling) выбирает одну из функций, описанных в [agent/tools_schema.py](agent/tools_schema.py): `search_places`, `rank_places`, `find_underserved_areas`.
3. **Tool execution** — Python-реализация в [agent/agent.py](agent/agent.py) (`TOOL_IMPL`) вызывает соответствующий код из [tools/](tools/).
4. **Tool result → LLM** — результат сериализуется в JSON и возвращается LLM как `role=tool` сообщение.
5. **Final response** — LLM формирует ответ на естественном языке, опираясь на данные тула.

Текущий цикл намеренно одношаговый (один tool call за запрос). Расширение до многошагового планирования — отдельная задача.

Если ни `OPENAI_API_KEY`, ни `LLM_BASE_URL` не заданы, агент падает в эвристический offline-роутинг (см. `_offline_route` в [agent/agent.py](agent/agent.py)). Это safety net, чтобы pipeline можно было прогнать end-to-end без сети и ключа.

### LLM backend: внешний или self-hosted

Агент использует OpenAI Python SDK, поэтому совместим с любым OpenAI-совместимым API. Поддерживаются три режима:

| Режим | Что задать | Когда выбирать |
| --- | --- | --- |
| External OpenAI | `OPENAI_API_KEY` | удобно, быстро, но нужен ключ и интернет |
| Self-hosted (Ollama / vLLM / LM Studio / llama.cpp) | `LLM_BASE_URL`, `LLM_MODEL` | приватность, бесплатно, нет лимитов |
| Offline fallback | ничего | нет ни ключа, ни локальной модели — работает эвристический роутинг |

#### Пример: локальный Ollama

```bash
# 1. поставить и запустить модель
ollama pull llama3.1:8b
ollama serve

# 2. в .env
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.1:8b

# 3. как обычно
python -m agent.agent "Find areas with low pharmacy coverage"
```

#### Пример: vLLM

```bash
python -m vllm.entrypoints.openai.api_server \
    --model meta-llama/Meta-Llama-3.1-8B-Instruct --port 8000

# .env
LLM_BASE_URL=http://localhost:8000/v1
LLM_MODEL=meta-llama/Meta-Llama-3.1-8B-Instruct
```

Важно: качество tool calling сильно зависит от модели. Llama 3.1 8B+ и Qwen 2.5 7B+ — это разумный минимум; модели поменьше часто ломают JSON-аргументы или игнорируют тулы. Если видите такие сбои — это сигнал переключиться на более сильную модель или больше работать с промптом в [agent/prompts.py](agent/prompts.py).

## How data flows through the system

```text
OSM (Overpass API)             ←— osmnx, может падать
        │
        ▼
scripts/download_osm.py        ─→ data/raw/*.csv, *.geojson
        │
        ▼
scripts/preprocess_data.py     ─→ data/processed/*.csv
        │
        ▼
tools/search.py::_load_places  ←— priority: processed → raw → sample_places.csv
        │
        ▼
tools/{search, ranking, coverage}.py    ←— ядро retrieval/ranking
        │
        ▼
agent/agent.py (tool calling)  /  app/app.py (Streamlit UI)
```

`tools/search.py::_load_places` ищет CSV в порядке `processed → raw → sample_places.csv`. Это значит, что **даже без интернета и без `download_osm.py`** система работает на встроенном snapshot (`data/sample_places.csv`, ~700 объектов вокруг Еревана).

## Golden path demo

Сценарий, который **гарантированно работает за 5 минут**, без OSM и без OPENAI_API_KEY:

```bash
pip install -r requirements.txt
python scripts/generate_sample_data.py    # уже в репо, можно пропустить
streamlit run app/app.py
# в UI нажать "Run golden-path demo (no LLM)"
```

Что увидите:

- карта Еревана с heatmap общей плотности POI,
- красные квадраты — ячейки с дефицитом аптек,
- таблица топ-10 underserved cells.

Тот же сценарий из CLI:

```bash
python -m agent.agent "Find areas with low pharmacy coverage"
```

Это onboarding, страховка и demo одновременно.

## Основные сценарии

- Find underserved areas — поиск районов с дефицитом услуг
- Build evening route — построение маршрута на вечер
- Search places by criteria — поиск мест по сложным критериям
- Compare ranking strategies — сравнение стратегий ранжирования

## Структура репозитория

```text
geo-ai-assistant/
│
├── README.md
├── requirements.txt
├── .env.example
│
├── data/
│   ├── sample_places.csv          # safety-net snapshot (~700 POI)
│   ├── raw/                       # сырые данные OSM
│   └── processed/                 # обработанные таблицы
│
├── notebooks/
│   ├── 01_data_collection.ipynb   # загрузка данных из OSM
│   ├── 02_eda.ipynb               # разведочный анализ
│   └── 03_ranking_experiments.ipynb
│
├── scripts/
│   ├── download_osm.py            # CLI-загрузчик OSM-объектов
│   ├── generate_sample_data.py    # генератор safety-net датасета
│   └── preprocess_data.py
│
├── tools/                         # tool-функции для LLM-агента
│   ├── search.py                  # search_places, nearest_places
│   ├── ranking.py                 # score_place, rank_by_score, rank_by_distance
│   ├── coverage.py                # find_underserved_areas
│   ├── filtering.py
│   └── geo_utils.py               # haversine, heatmap
│
├── agent/                         # LLM-агент и оркестрация
│   ├── prompts.py
│   ├── tools_schema.py            # OpenAI tool schema
│   └── agent.py                   # один цикл tool calling + offline fallback
│
├── app/                           # пользовательский интерфейс
│   ├── app.py                     # Streamlit + sidebar + golden path
│   └── map_visualization.py       # folium maps
│
└── evaluation/                    # бенчмарки
    ├── benchmark_queries.json
    └── evaluate.py
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# открыть .env и подставить OPENAI_API_KEY (опционально — без ключа работает offline-роутинг)
```

Python 3.10+ рекомендован.

## Как собрать данные

```bash
python scripts/download_osm.py --city "Yerevan, Armenia" --categories cafe restaurant pharmacy bar
```

Результат — в `data/raw/` (CSV + GeoJSON). Альтернатива — notebook `notebooks/01_data_collection.ipynb`.

Если Overpass / osmnx недоступны, в `data/sample_places.csv` уже лежит сгенерированный snapshot — система работает на нём автоматически.

## Как запускать demo

Интерактивный UI:

```bash
streamlit run app/app.py
```

В sidebar: выбор города, категорий и стратегии ранжирования. В основной панели — preset-запросы и кнопка golden-path демо.

CLI-демо агента:

```bash
python -m agent.agent "Find areas with low pharmacy coverage"
python -m agent.agent "Find quiet cafe near metro"
```

## Примеры запросов

- "Find areas with low pharmacy coverage"
- "Plan evening route with restaurant and bar"
- "Find quiet cafe near metro"
- "Compare restaurant density in two districts"

## Research section

Базовые направления исследования:

- **Метрики ранжирования** — сравнение стратегий `rank_by_distance` vs `rank_by_score` (composite `0.7*rating − 0.3*distance`); precision@k на benchmark-запросах из `evaluation/benchmark_queries.json`.
- **Coverage / underserved areas** — насколько устойчив grid-based score к выбору `grid_size_deg`; что меняется при переходе с равномерной сетки на гексы H3.
- **Полнота данных** — влияет ли заполненность OSM-полей (`name`, `opening_hours`, рейтинги из внешних источников) на качество рекомендаций.
- **LLM-роутинг** — как часто tool calling выбирает правильный инструмент; где LLM галлюцинирует координаты и как это смягчить prompt-инжинирингом.

Результаты экспериментов фиксируются в [notebooks/03_ranking_experiments.ipynb](notebooks/03_ranking_experiments.ipynb) и резюмируются здесь по мере накопления.

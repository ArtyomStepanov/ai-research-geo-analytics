"""OpenAI-compatible tool schema definitions for the agent."""


from lib.data_types.agent_tools_schema import (
    DistanceRequest,
    FilterRequest,
    GeocodeRequest,
    HeatmapRequest,
    NearestHexesRequest,
    NearestPlacesRequest,
    OpportunityGridRequest,
    RankPlacesRequest,
    SearchByNameRequest,
    SearchPlacesRequest,
    to_tool_schema,
)

TOOLS = [
    to_tool_schema(
        GeocodeRequest,
        "geocode",
        "Преобразует название места или ориентира (топоним) в координаты lat/lon. "
        "Вызывай ПЕРВЫМ, если пользователь указал название места вместо числовых координат, "
        "затем передай полученные lat/lon в search_places или nearest_places."
    ),
    to_tool_schema(
        SearchPlacesRequest,
        "search_places",
        "Поиск объектов инфраструктуры (кафе, ресторан, фастфуд, аптека, бар, ...) из локального датасета. "
        "Опционально фильтрует по расстоянию от опорной точки."
    ),
    to_tool_schema(
        NearestPlacesRequest,
        "nearest_places",
        "Поиск N ближайших объектов инфраструктуры (кафе, ресторан, фастфуд, аптека, бар, ...) рядом с точкой из локального датасета."
    ),
    to_tool_schema(
        SearchByNameRequest,
        "search_by_name",
        "Поиск объектов инфраструктуры (кафе, ресторан, фастфуд, аптека, бар, ...) из локального датасета по названию. "
        "Опционально фильтрует по расстоянию от опорной точки."
    ),
    to_tool_schema(
        RankPlacesRequest,
        "rank_places",
        "Ранжирует ранее полученный список мест. "
        "Стратегия: 'distance' (по возрастанию distance_km) или 'score' (по модели Хаффа)."
    ),
    to_tool_schema(
        NearestHexesRequest,
        "nearest_hexes",
        "Возвращает метрики opportunity-grid для гексагона и его соседей. "
        "radius=1 возвращает целевой гекс ('Ц') + 6 соседей, каждый с полем 'label': "
        "'С'/'В'/'ЮВ'/'Ю'/'З'/'СЗ' — направление по компасу от центра. "
        "ИСПОЛЬЗУЙ ЭТИ МЕТКИ в ответах и пиши hex_id в скобках рядом с меткой: «Гекс СВ (hex_id)». "
        "Требует предварительного вычисления opportunity_grid."
    ),
    to_tool_schema(
        OpportunityGridRequest,
        "opportunity_grid",
        "Вычисляет карту возможностей на гексагональной сетке для категории. "
        "Стратегия 'implant' — для задач выбора локации: 'где открыть', 'недообслуживаемые зоны', "
        "'низкое покрытие', 'найти лучшее место', 'где нам не хватает X'. "
        "Стратегия 'aggregate' — для анализа конкурентной среды: 'показать позиции конкурентов', "
        "'насыщенность рынка', 'где конкуренты сильны', 'текущий ландшафт конкурентов'."
    ),
    to_tool_schema(
        FilterRequest,
        "filter_places",
        "Фильтрует места по категории или рейтингу."
    ),
    to_tool_schema(
        DistanceRequest,
        "compute_distance",
        "Вычисляет расстояние между двумя точками. Возвращает число."
    ),
    to_tool_schema(
        HeatmapRequest,
        "build_heatmap",
        "Строит тепловую карту мест, уже полученных через search_places/nearest_places. "
        "НЕ использовать для анализа покрытия или возможностей — для этого используй opportunity_grid."
    ),
]


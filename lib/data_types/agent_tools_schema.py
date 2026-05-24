"""Pydantic-модели для схем инструментов OpenAI."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from lib.data_types import Place

class SearchPlacesRequest(BaseModel):
    """Поиск объектов из локального датасета с опциональным гео-фильтром."""
    category: list[str] = Field(
        default_factory=list,
        description="Теги OSM amenity, например ['cafe','restaurant']. Пусто = любые.",
    )
    name: str | None = Field(
        None, description="Подстрока/нечёткое совпадение названия объекта, например 'Starbucks'."
    )
    near_lat: float | None = Field(None, description="Широта якорной точки.")
    near_lon: float | None = Field(None, description="Долгота якорной точки.")
    max_distance_km: float | None = Field(
        None, description="Оставить только места в пределах этого радиуса от якорной точки."
    )
    limit: int = Field(10, ge=1, description="Максимальное количество результатов.")


class NearestPlacesRequest(BaseModel):
    """Найти N ближайших объектов к точке. Якорная точка ОБЯЗАТЕЛЬНА."""
    near_lat: float = Field(..., description="Широта якорной точки (обязательна).")
    near_lon: float = Field(..., description="Долгота якорной точки (обязательна).")
    category: list[str] = Field(
        default_factory=list, description="Теги OSM amenity. Пусто = любые."
    )
    limit: int = Field(5, ge=1, description="Сколько ближайших вернуть.")


class SearchByNameRequest(BaseModel):
    """Поиск объектов по названию. `name` ОБЯЗАТЕЛЕН."""
    name: str = Field(..., description="Название объекта для нечёткого поиска (обязательно).")
    near_lat: float | None = Field(None, description="Необязательная широта якорной точки.")
    near_lon: float | None = Field(None, description="Необязательная долгота якорной точки.")


class RankPlacesRequest(BaseModel):
    """Ранжировать места, возвращённые предыдущим инструментом поиска."""
    places: list[Place] = Field(
        ...,
        description="Список результатов предыдущего инструмента поиска/фильтрации. "
                    "Передавать без изменений; НЕ добавлять записи.",
    )
    strategy: Literal["distance", "score"] = Field(
        ..., description="'distance' = сначала ближайшие; 'score' = комбинированный."
    )


class UnderservedAreasRequest(BaseModel):
    """Найти ячейки сетки, где категория объектов недостаточно представлена."""
    category: list[str] = Field(
        ...,
        description="Теги объектов, например ['pharmacy']. Список для согласованности "
                    "с инструментами поиска (один концепт = один тип везде).",
    )
    top_k: int = Field(10, ge=1, description="Сколько топ-ячеек вернуть.")


class NearestHexesRequest(BaseModel):
    """Получить гексагон и его окружение из сетки возможностей."""
    hex_id: str = Field(..., description="Идентификатор ячейки H3 для анализа.")
    radius: int = Field(1, ge=0, le=3,
                        description="Радиус кольца (0=только целевая, 1=целевая+6 соседей).")


class OpportunityGridRequest(BaseModel):
    """Рассчитать гексагональную сетку возможностей для выбора локации."""
    category: str = Field(
        ...,
        description="Тип целевого объекта, например 'pharmacy', 'cafe', 'bar'. Используется для фильтрации конкурентов."
    )
    hex_resolution: int = Field(
        8, ge=5, le=12,
        description="Разрешение H3 (8 ~ 0.74 км сторона ячейки). Больше = мельче сетка, меньше = крупнее."
    )
    demand_threshold: float = Field(
        0.0,
        description="Минимальный балл спроса для отображения гексагона на карте."
    )
    strategy: Literal["implant", "aggregate"] = Field(
        "implant",
        description=(
            "Стратегия оценки. "
            "Используйте 'implant' для запросов 'где открыть / лучшая локация / недообслуживаемые районы': "
            "симулирует открытие нового заведения и оценивает ожидаемых клиентов. "
            "Используйте 'aggregate' для запросов 'показать карту конкурентов / насыщенность рынка / позиции конкурентов': "
            "агрегирует силу существующих заведений по близости."
        )
    )


class FilterRequest(BaseModel):
    """Фильтровать места, возвращённые предыдущим инструментом поиска."""
    places: list[Place] = Field(
        ..., description="Результат предыдущего инструмента; передавать без изменений."
    )
    strategy: Literal["category", "rating"] = Field(
        "rating", description="Режим фильтрации."
    )
    category: list[str] | None = Field(
        None, description="Обязательно если strategy='category'. Список тегов объектов."
    )
    min_rating: float | None = Field(
        None, ge=0, le=5, description="Обязательно если strategy='rating'."
    )


class DistanceRequest(BaseModel):
    """Расстояние по большому кругу между двумя точками [lat, lon], в км."""
    p1: list[float] = Field(..., min_length=2, max_length=2,
                            description="[lat, lon] первой точки.")
    p2: list[float] = Field(..., min_length=2, max_length=2,
                            description="[lat, lon] второй точки.")


class HeatmapRequest(BaseModel):
    """Построить HTML тепловую карту из взвешенных точек; возвращает путь к файлу."""
    points: list[list[float]] = Field(
        ...,
        description="Список [lat, lon] или [lat, lon, weight]. Минимум 1 точка.",
    )
    radius: int = Field(12, ge=1, description="Радиус тепловой точки (пикселей).")
    legend: bool = Field(False, description="Показать оверлей легенды.")


class GeocodeRequest(BaseModel):
    """Преобразовать название места или адрес в координаты lat/lon."""
    location: str = Field(..., description="Название места или адрес, например 'Площадь Республики, Ереван'.")
    city_hint: str = Field("", description="Необязательный город для уточнения поиска, например 'Ереван'.")


# Helper function to convert Pydantic model to OpenAI tool schema
def to_tool_schema(model_class: type[BaseModel], name: str, description: str) -> dict:
    """Конвертировать Pydantic-модель в схему инструмента, совместимую с OpenAI."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": model_class.model_json_schema(),
            "strict": True
        }
    }

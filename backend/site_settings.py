"""Настройки сайта, которые администратор меняет в панели:
акции, цены калькулятора и карточки прайса.

Значения по умолчанию совпадают с src/siteSettings.js — сайт показывает их,
пока не загрузил настройки с сервера.
"""

import json
import secrets
import threading

from pydantic import BaseModel, ConfigDict, Field, model_validator

import db


DEFAULTS = {
    "hero": {
        "id": "hero_discount_20",
        "value": "20%",
        "title": "Месяц мега-скидок",
        "text": "Заявка на бесплатный замер с главного экрана",
    },
    "promotions": [
        {
            "id": "svo_discount_10",
            "value": "10%",
            "title": "Скидка участникам СВО и семьям",
            "text": "Скидка 10% на услуги компании при заказе от 9 500 ₽. Условия уточняйте у специалиста.",
            "button": "Получить скидку",
        },
        {
            "id": "combined_discount_25",
            "value": "25%",
            "title": "Суммируем скидки",
            "text": "Комбинация акционных условий 10 + 10 + 5. Подробности расскажет инженер по замеру.",
            "button": "Узнать условия",
        },
        {
            "id": "successful_day_12",
            "value": "12%",
            "title": "«Успешный день»",
            "text": "При заключении договора в день замера действует скидка 12% на работы «под ключ».",
            "button": "Записаться на замер",
        },
        {
            "id": "design_project_3d",
            "value": "3D",
            "title": "Дизайн-проект бесплатно",
            "text": "Для нестандартных конструкций подготовим визуализацию будущего потолка.",
            "button": "Хочу проект",
        },
        {
            "id": "lights_discount_20",
            "value": "20%",
            "title": "Светильники со скидкой",
            "text": "При покупке натяжного потолка специальные LED-светильники доступны со скидкой 20%.",
            "button": "Подобрать освещение",
        },
        {
            "id": "measurement_bonus_500",
            "value": "500 ₽",
            "title": "Дополнительная скидка за замер",
            "text": "Запишитесь на бесплатный замер и получите ещё одну персональную выгоду.",
            "button": "Вызвать замерщика",
        },
    ],
    "calculator": {
        "types": [
            {"name": "Матовый", "price_per_m2": 450},
            {"name": "Глянцевый", "price_per_m2": 500},
            {"name": "Сатиновый", "price_per_m2": 480},
            {"name": "Тканевый", "price_per_m2": 900},
        ],
        "price_per_corner": 150,
        "price_per_light": 300,
    },
    "price_cards": [
        {"room": "ГОСТИНАЯ", "title": "Многоуровневый потолок", "price": "от 9 000 ₽"},
        {"room": "СПАЛЬНЯ", "title": "Тканевый потолок", "price": "от 13 000 ₽"},
        {"room": "ДЕТСКАЯ", "title": "Фотопечать", "price": "от 7 200 ₽"},
        {"room": "КУХНЯ", "title": "Глянцевый потолок", "price": "от 4 900 ₽"},
        {"room": "ПРИХОЖАЯ", "title": "Световые линии", "price": "от 4 900 ₽"},
    ],
}

PRICE_CARD_COUNT = len(DEFAULTS["price_cards"])


class Strict(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class Hero(Strict):
    id: str = Field(pattern=r"^[a-z0-9_]{1,40}$")
    value: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=100)
    text: str = Field(default="", max_length=300)


class Promotion(Strict):
    # Пустой ID у новой акции сервер заполнит сам
    id: str = Field(default="", pattern=r"^[a-z0-9_]{0,40}$")
    value: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=100)
    text: str = Field(default="", max_length=300)
    button: str = Field(min_length=1, max_length=40)


class CeilingType(Strict):
    name: str = Field(min_length=1, max_length=40)
    price_per_m2: int = Field(ge=0, le=100_000)


class Calculator(Strict):
    types: list[CeilingType] = Field(min_length=1, max_length=20)
    price_per_corner: int = Field(ge=0, le=100_000)
    price_per_light: int = Field(ge=0, le=100_000)

    @model_validator(mode="after")
    def unique_names(self):
        names = [t.name for t in self.types]

        if len(names) != len(set(names)):
            raise ValueError("Названия типов потолка не должны повторяться")

        return self


class PriceCard(Strict):
    room: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=60)
    price: str = Field(min_length=1, max_length=30)


class SiteSettings(Strict):
    hero: Hero
    promotions: list[Promotion] = Field(max_length=20)
    calculator: Calculator
    price_cards: list[PriceCard] = Field(
        min_length=PRICE_CARD_COUNT, max_length=PRICE_CARD_COUNT
    )


_cache: dict | None = None
_cache_lock = threading.Lock()


def get() -> dict:
    global _cache

    with _cache_lock:
        if _cache is None:
            row = db.query_one("SELECT value FROM settings WHERE key = 'site'")
            _cache = json.loads(row["value"]) if row else DEFAULTS

        return _cache


def save(data: SiteSettings, user_id: int) -> dict:
    global _cache

    value = data.model_dump()

    for promotion in value["promotions"]:
        if not promotion["id"]:
            promotion["id"] = "promo_" + secrets.token_hex(4)

    ids = [p["id"] for p in value["promotions"]] + [value["hero"]["id"]]

    if len(ids) != len(set(ids)):
        raise ValueError("ID акций не должны повторяться")

    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO settings (key, value, updated_at, updated_by) VALUES ('site', ?, ?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value,"
            " updated_at = excluded.updated_at, updated_by = excluded.updated_by",
            (json.dumps(value, ensure_ascii=False), db.now(), user_id),
        )

    with _cache_lock:
        _cache = value

    return value


def find_promotion(promotion_id: str) -> dict | None:
    settings = get()

    if settings["hero"]["id"] == promotion_id:
        return settings["hero"]

    for promotion in settings["promotions"]:
        if promotion["id"] == promotion_id:
            return promotion

    return None


def find_promotion_by_title(title: str, value: str) -> dict | None:
    settings = get()

    for promotion in [settings["hero"], *settings["promotions"]]:
        if promotion["title"] == title and promotion["value"] == value:
            return promotion

    return None


def ceiling_prices() -> dict[str, int]:
    return {t["name"]: t["price_per_m2"] for t in get()["calculator"]["types"]}

import asyncio
import logging
import math
import os
import time
import uuid
from collections import deque
from contextlib import asynccontextmanager
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator


# Переменные окружения нужны модулям ниже уже при импорте
load_dotenv()

import admin_api  # noqa: E402
import chat_api  # noqa: E402
import crm  # noqa: E402
import db  # noqa: E402
import site_settings  # noqa: E402
import telegram_bot  # noqa: E402


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("hameleon.leads")

# httpx пишет в журнал адрес каждого запроса, а в адресе Telegram API
# содержится токен бота. Оставляем от httpx только предупреждения.
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    polling = asyncio.create_task(telegram_bot.polling_loop())

    yield

    polling.cancel()


app = FastAPI(
    title="Хамелеон API",
    version="1.0.0",
    lifespan=lifespan,
    # Служебная документация API не нужна посетителям
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.include_router(admin_api.router)
app.include_router(chat_api.router)


# CORS нужен только при локальной разработке, когда фронтенд
# и API работают на разных портах. В production запросы идут
# с того же домена, поэтому переменная CORS_ORIGINS не задаётся.
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", "").split(",")
    if origin.strip()
]

if CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )


# Акции и цены калькулятора хранятся в настройках сайта (site_settings.py),
# их меняет администратор в панели. Сайт присылает только ID акции
# и параметры потолка, а условия и цену сервер берёт из настроек.

class CalculatorData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: float = Field(ge=1, le=100)
    length: float = Field(ge=1, le=100)
    ceiling_type: str = Field(min_length=1, max_length=40)
    corners: int = Field(ge=4, le=100)
    lights: int = Field(ge=0, le=500)

    # Старые версии сайта присылали площадь и цену. Поля принимаются,
    # чтобы не ломать открытые в браузерах страницы, но не используются:
    # сервер всегда считает их сам.
    area: float | None = Field(default=None, exclude=True)
    estimated_price: int | None = Field(default=None, exclude=True)

    @field_validator("ceiling_type")
    @classmethod
    def known_ceiling_type(cls, value: str) -> str:
        if value not in site_settings.ceiling_prices():
            raise ValueError("Неизвестный тип потолка")

        return value

    def calculated_area(self) -> float:
        return math.floor(self.width * self.length * 10 + 0.5) / 10

    def calculated_price(self) -> int:
        calculator = site_settings.get()["calculator"]
        total = (
            self.calculated_area() * site_settings.ceiling_prices()[self.ceiling_type]
            + self.corners * calculator["price_per_corner"]
            + self.lights * calculator["price_per_light"]
        )

        return max(0, math.floor(total / 100 + 0.5) * 100)


class PromotionData(BaseModel):
    """Акция в старом формате (текстом). Её присылают страницы,
    открытые до обновления сайта, и акции, сохранённые в браузере."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    title: str = Field(min_length=1, max_length=100)
    value: str = Field(min_length=1, max_length=20)
    text: str | None = Field(default=None, max_length=300)


class LeadCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=2, max_length=100)
    phone: str = Field(min_length=10, max_length=30)
    source: Literal[
        "contact",
        "calculator",
        "promotion",
        "hero_discount",
    ] = "contact"
    calculator: CalculatorData | None = None
    promotion_id: str | None = Field(default=None, max_length=40)
    promotion: PromotionData | None = None

    # Защита от ботов: скрытое поле, которое человек не видит и не заполняет,
    # и время от открытия страницы до отправки формы
    website: str | None = Field(default=None, max_length=200)
    form_elapsed_ms: int | None = Field(default=None, ge=0)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        allowed = set("0123456789+-() ")

        if any(ch not in allowed for ch in value):
            raise ValueError("Некорректный номер телефона")

        digits = "".join(ch for ch in value if ch.isdigit())

        if len(digits) not in (10, 11):
            raise ValueError("Некорректный номер телефона")

        return value

    @field_validator("promotion_id")
    @classmethod
    def known_promotion(cls, value: str | None) -> str | None:
        if value is not None and not site_settings.find_promotion(value):
            raise ValueError("Неизвестная акция")

        return value


# Человек не успевает заполнить форму быстрее, чем за 2 секунды
MIN_FORM_FILL_MS = 2000

# Ограничение частоты заявок. Хранится в памяти процесса и сбрасывается
# при перезапуске API — для одного процесса uvicorn этого достаточно.
RATE_WINDOW_SECONDS = 10 * 60
RATE_LIMIT_PER_IP = 5
RATE_LIMIT_TOTAL = 30

_requests_by_ip: dict[str, deque] = {}
_requests_total: deque = deque()


def _prune(timestamps: deque, now: float) -> None:
    while timestamps and now - timestamps[0] > RATE_WINDOW_SECONDS:
        timestamps.popleft()


def check_rate_limit(client_ip: str) -> bool:
    """Возвращает False, если лимит заявок превышен."""
    now = time.monotonic()

    _prune(_requests_total, now)

    for ip in list(_requests_by_ip):
        _prune(_requests_by_ip[ip], now)

        if not _requests_by_ip[ip]:
            del _requests_by_ip[ip]

    ip_requests = _requests_by_ip.setdefault(client_ip, deque())

    if (
        len(ip_requests) >= RATE_LIMIT_PER_IP
        or len(_requests_total) >= RATE_LIMIT_TOTAL
    ):
        return False

    ip_requests.append(now)
    _requests_total.append(now)

    return True


@app.get("/")
def root():
    return {
        "status": "ok",
        "message": "Хамелеон API работает",
    }


@app.get("/api/site/settings")
def public_site_settings(response: Response):
    """Акции, цены калькулятора и прайс для страниц сайта."""
    response.headers["Cache-Control"] = "public, max-age=60"
    return site_settings.get()


@app.get("/api/health")
def health():
    return {
        "status": "ok",
    }


SOURCE_LABELS = {
    "contact": "форма «Бесплатный замер»",
    "calculator": "калькулятор",
    "promotion": "раздел «Акции»",
    "hero_discount": "главный экран",
}


def resolve_promotion(lead: LeadCreate) -> dict | None:
    """Находит акцию в списке сервера. Тексту из браузера не доверяем."""
    if lead.promotion_id:
        return site_settings.find_promotion(lead.promotion_id)

    if lead.promotion:
        # Старый формат: ищем акцию с таким же названием и выгодой
        promotion = site_settings.find_promotion_by_title(
            lead.promotion.title, lead.promotion.value
        )

        if promotion:
            return promotion

        logger.warning("получена неизвестная акция, она не будет указана")

    return None


def format_lead_message(lead: LeadCreate) -> str:
    source_label = SOURCE_LABELS.get(lead.source, lead.source)
    promotion = resolve_promotion(lead)

    if promotion:
        message = (
            "🔥 Новая заявка по акции — Хамелеон\n\n"
            f"👤 Имя: {lead.name}\n"
            f"📞 Телефон: {lead.phone}\n\n"
            f"🎁 Акция: {promotion['title']}\n"
            f"💰 Предложение: {promotion['value']}\n\n"
            f"{promotion['text']}\n"
        )
    else:
        message = (
            "🦎 Новая заявка — Хамелеон\n\n"
            f"👤 Имя: {lead.name}\n"
            f"📞 Телефон: {lead.phone}\n"
        )

    if lead.calculator:
        calculator = lead.calculator
        formatted_price = f"{calculator.calculated_price():,}".replace(",", " ")

        message += (
            "\n📐 Расчёт потолка:\n"
            f"Ширина: {calculator.width} м\n"
            f"Длина: {calculator.length} м\n"
            f"Площадь: {calculator.calculated_area()} м²\n"
            f"Тип потолка: {calculator.ceiling_type}\n"
            f"Углов: {calculator.corners}\n"
            f"Светильников: {calculator.lights}\n"
            f"Предварительная стоимость: {formatted_price} ₽\n"
        )

    message += f"\n📍 Источник: {source_label}"

    return message


def lead_record_fields(lead: LeadCreate) -> tuple[str | None, dict | None]:
    """Акция и расчёт в виде, удобном для хранения и показа в панели."""
    promotion = resolve_promotion(lead)
    promotion_text = (
        f"{promotion['title']} ({promotion['value']})" if promotion else None
    )

    details = None

    if lead.calculator:
        calculator = lead.calculator
        details = {
            "Ширина, м": calculator.width,
            "Длина, м": calculator.length,
            "Площадь, м²": calculator.calculated_area(),
            "Тип потолка": calculator.ceiling_type,
            "Углов": calculator.corners,
            "Светильников": calculator.lights,
            "Стоимость, ₽": calculator.calculated_price(),
        }

    return promotion_text, details


@app.post("/api/leads")
async def create_lead(lead: LeadCreate, request: Request):
    request_id = uuid.uuid4().hex[:12]

    # Имя, телефон и детали расчёта в журнал не пишем
    logger.info(
        "request_id=%s получена заявка: source=%s",
        request_id,
        lead.source,
    )

    if lead.website:
        # Бот заполнил скрытое поле. Отвечаем «успешно», чтобы он
        # не подбирал обход, но в Telegram ничего не отправляем.
        logger.warning(
            "request_id=%s отклонено: заполнено скрытое поле",
            request_id,
        )

        return {
            "status": "success",
            "message": "Заявка отправлена",
        }

    if (
        lead.form_elapsed_ms is not None
        and lead.form_elapsed_ms < MIN_FORM_FILL_MS
    ):
        logger.warning(
            "request_id=%s отклонено: форма заполнена за %d мс",
            request_id,
            lead.form_elapsed_ms,
        )

        raise HTTPException(
            status_code=400,
            detail="Не удалось отправить заявку. Попробуйте ещё раз.",
        )

    client_ip = request.client.host if request.client else "unknown"

    if not check_rate_limit(client_ip):
        logger.warning(
            "request_id=%s отклонено: превышен лимит заявок",
            request_id,
        )

        raise HTTPException(
            status_code=429,
            detail="Слишком много заявок. Попробуйте через несколько минут.",
        )

    message = format_lead_message(lead)

    # Сначала сохраняем заявку: даже если Telegram недоступен,
    # она не потеряется и будет видна в панели
    lead_id = None

    try:
        promotion_text, details = lead_record_fields(lead)
        lead_id = crm.create_lead(
            SOURCE_LABELS.get(lead.source, lead.source),
            lead.name,
            lead.phone,
            promotion_text,
            details,
        )
        logger.info("request_id=%s сохранена как заявка №%s", request_id, lead_id)
    except Exception as error:
        logger.error(
            "request_id=%s заявка не сохранена в базу: %s",
            request_id,
            type(error).__name__,
        )

    try:
        if lead_id:
            delivered = await telegram_bot.notify_lead(lead_id, message)
        else:
            delivered = await telegram_bot.broadcast(message, "lead", 0)
    except telegram_bot.TelegramError as error:
        logger.error("request_id=%s Telegram: %s", request_id, error)
        delivered = 0

    if not delivered and not lead_id:
        raise HTTPException(
            status_code=500,
            detail="Не удалось отправить заявку",
        )

    logger.info(
        "request_id=%s заявка доставлена в %d чат(ов)",
        request_id,
        delivered,
    )

    return {
        "status": "success",
        "message": "Заявка отправлена",
    }

import logging
import os
import time
import uuid
from collections import deque
from typing import Literal

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, field_validator


load_dotenv()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("hameleon.leads")


app = FastAPI(
    title="Хамелеон API",
    version="1.0.0",
)


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


TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

TELEGRAM_CHAT_IDS = [
    chat_id.strip()
    for chat_id in os.getenv(
        "TELEGRAM_CHAT_IDS",
        os.getenv("TELEGRAM_CHAT_ID", ""),
    ).split(",")
    if chat_id.strip()
]


class CalculatorData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    width: float = Field(ge=1, le=100)
    length: float = Field(ge=1, le=100)
    area: float | None = Field(default=None, ge=0, le=10000)
    ceiling_type: Literal[
        "Матовый",
        "Глянцевый",
        "Сатиновый",
        "Тканевый",
    ]
    corners: int = Field(ge=4, le=100)
    lights: int = Field(ge=0, le=500)
    estimated_price: int | None = Field(default=None, ge=0, le=100_000_000)


class PromotionData(BaseModel):
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


def format_lead_message(lead: LeadCreate) -> str:
    source_label = SOURCE_LABELS.get(lead.source, lead.source)

    if lead.promotion:
        promotion = lead.promotion

        return (
            "🔥 Новая заявка по акции — Хамелеон\n\n"
            f"👤 Имя: {lead.name}\n"
            f"📞 Телефон: {lead.phone}\n\n"
            f"🎁 Акция: {promotion.title}\n"
            f"💰 Предложение: {promotion.value}\n\n"
            f"{promotion.text or ''}\n\n"
            f"📍 Источник: {source_label}"
        )

    message = "🦎 Новая заявка — Хамелеон\n\n"

    if lead.name:
        message += f"👤 Имя: {lead.name}\n"

    if lead.phone:
        message += f"📞 Телефон: {lead.phone}\n"

    message += f"📍 Источник: {source_label}\n"

    if lead.calculator:
        calculator = lead.calculator
        price = calculator.estimated_price

        if price is not None:
            formatted_price = f"{price:,}".replace(",", " ")
        else:
            formatted_price = "не рассчитана"

        message += (
            "\n📐 Расчёт потолка:\n"
            f"Ширина: {calculator.width} м\n"
            f"Длина: {calculator.length} м\n"
            f"Площадь: {calculator.area} м²\n"
            f"Тип потолка: {calculator.ceiling_type}\n"
            f"Углов: {calculator.corners}\n"
            f"Светильников: {calculator.lights}\n"
            f"Предварительная стоимость: {formatted_price} ₽\n"
        )

    return message


async def send_to_telegram(message: str, request_id: str) -> int:
    """Отправляет сообщение во все чаты и возвращает число успешных доставок.

    Ошибка возникает только если сообщение не дошло ни до одного чата:
    иначе повтор заявки приведёт к дублям у тех, кто её уже получил.
    """
    if not TELEGRAM_BOT_TOKEN:
        raise RuntimeError(
            "В .env отсутствует TELEGRAM_BOT_TOKEN"
        )

    if not TELEGRAM_CHAT_IDS:
        raise RuntimeError(
            "В .env отсутствует TELEGRAM_CHAT_IDS"
        )

    url = (
        f"https://api.telegram.org/"
        f"bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    )

    delivered = 0
    failed = 0

    async with httpx.AsyncClient() as client:
        for chat_id in TELEGRAM_CHAT_IDS:
            payload = {
                "chat_id": chat_id,
                "text": message,
            }

            try:
                response = await client.post(
                    url,
                    json=payload,
                    timeout=10.0,
                )

                if response.status_code == 200:
                    delivered += 1
                else:
                    failed += 1
                    # Ответ Telegram и chat_id не пишем в журнал
                    logger.warning(
                        "request_id=%s Telegram вернул статус %s",
                        request_id,
                        response.status_code,
                    )

            except httpx.HTTPError as error:
                failed += 1
                # Текст исключения может содержать URL с токеном бота
                logger.warning(
                    "request_id=%s ошибка соединения с Telegram: %s",
                    request_id,
                    type(error).__name__,
                )

    if delivered == 0:
        raise RuntimeError("Заявка не доставлена ни в один чат Telegram")

    if failed:
        logger.warning(
            "request_id=%s частичная доставка: успешно %d, ошибок %d",
            request_id,
            delivered,
            failed,
        )

    return delivered


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

    try:
        delivered = await send_to_telegram(message, request_id)

    except Exception as error:
        logger.error(
            "request_id=%s заявка не отправлена: %s",
            request_id,
            error,
        )

        raise HTTPException(
            status_code=500,
            detail="Не удалось отправить заявку в Telegram",
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

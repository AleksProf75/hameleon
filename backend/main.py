import os

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


load_dotenv()


app = FastAPI(
    title="Хамелеон API",
    version="1.0.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
    width: float | None = None
    length: float | None = None
    area: float | None = None
    ceiling_type: str | None = None
    corners: int | None = None
    lights: int | None = None
    estimated_price: int | None = None


class PromotionData(BaseModel):
    title: str
    value: str
    text: str | None = None


class LeadCreate(BaseModel):
    name: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )
    phone: str | None = Field(
        default=None,
        min_length=10,
        max_length=30,
    )
    source: str = "contact"
    calculator: CalculatorData | None = None
    promotion: PromotionData | None = None


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


def format_lead_message(lead: LeadCreate) -> str:
    if lead.source == "promotion" and lead.promotion:
        promotion = lead.promotion

        return (
            "🔥 Новая заявка по акции — Хамелеон\n\n"
            f"🎁 Акция: {promotion.title}\n"
            f"💰 Предложение: {promotion.value}\n\n"
            f"{promotion.text or ''}\n\n"
            "📍 Источник: раздел «Акции»"
        )

    message = "🦎 Новая заявка — Хамелеон\n\n"

    if lead.name:
        message += f"👤 Имя: {lead.name}\n"

    if lead.phone:
        message += f"📞 Телефон: {lead.phone}\n"

    message += f"📍 Источник: {lead.source}\n"

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


async def send_to_telegram(message: str):
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

    errors = []

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

                if response.status_code != 200:
                    errors.append(
                        f"{chat_id}: {response.text}"
                    )

            except Exception as error:
                errors.append(
                    f"{chat_id}: {error}"
                )

    if errors:
        raise RuntimeError(
            "Ошибки Telegram: " + "; ".join(errors)
        )


@app.post("/api/leads")
async def create_lead(lead: LeadCreate):
    print("Получена заявка:")
    print(lead.model_dump())

    message = format_lead_message(lead)

    try:
        await send_to_telegram(message)

    except Exception as error:
        print("Ошибка отправки в Telegram:")
        print(error)

        raise HTTPException(
            status_code=500,
            detail="Не удалось отправить заявку в Telegram",
        )

    return {
        "status": "success",
        "message": "Заявка отправлена",
    }
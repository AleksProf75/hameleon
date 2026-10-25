"""Онлайн-чат для посетителей сайта: /api/chat/...

Посетитель получает секретный токен чата при первом сообщении
и передаёт его в заголовке X-Chat-Token (не в адресе страницы).
"""

import logging

from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field

import crm
import telegram_bot
from ratelimit import SlidingLimiter


logger = logging.getLogger("hameleon.chat")

router = APIRouter(prefix="/api/chat")

# Новых чатов с одного адреса — не больше 3 за 10 минут,
# сообщений — не больше 20 за 10 минут, по сайту — 200 за 10 минут
new_chat_limiter = SlidingLimiter(3, 10 * 60)
message_limiter = SlidingLimiter(20, 10 * 60)
total_limiter = SlidingLimiter(200, 10 * 60)


class StartChat(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str | None = Field(default=None, max_length=100)
    text: str = Field(min_length=1, max_length=1000)
    website: str | None = Field(default=None, max_length=200)


class ChatMessage(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    text: str = Field(min_length=1, max_length=1000)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _check_limits(request: Request, limiter: SlidingLimiter) -> None:
    ip = _client_ip(request)

    if not limiter.allow(ip) or not total_limiter.allow("all"):
        raise HTTPException(
            status_code=429,
            detail="Слишком много сообщений. Попробуйте через несколько минут.",
        )


def _require_chat(token: str | None) -> dict:
    chat = crm.chat_by_token(token) if token else None

    if not chat:
        raise HTTPException(status_code=404, detail="Чат не найден")

    return chat


def _public_messages(chat_id: int, after: int) -> list[dict]:
    return [
        {
            "id": message["id"],
            "author": message["author"],
            "text": message["text"],
            "time": crm.local_time(message["created_at"])[-5:],
            # Посетителю показываем только имя менеджера, без логина
            "manager": message["user_name"] if message["author"] == "manager" else None,
        }
        for message in crm.chat_messages(chat_id, after)
    ]


@router.post("/start")
async def start_chat(data: StartChat, request: Request):
    if data.website:
        # Бот заполнил скрытое поле
        raise HTTPException(status_code=400, detail="Не удалось начать чат")

    _check_limits(request, new_chat_limiter)

    chat_id, token = crm.create_chat(data.name or None)
    crm.add_chat_message(chat_id, "visitor", data.text)
    logger.info("новый чат №%s", chat_id)

    try:
        await telegram_bot.notify_chat_message(chat_id, data.name, data.text)
    except telegram_bot.TelegramError as error:
        logger.warning("чат №%s: уведомление не отправлено: %s", chat_id, error)

    return {"token": token, "messages": _public_messages(chat_id, 0)}


@router.post("/messages")
async def send_message(
    data: ChatMessage,
    request: Request,
    x_chat_token: str | None = Header(default=None),
):
    chat = _require_chat(x_chat_token)
    _check_limits(request, message_limiter)

    crm.add_chat_message(chat["id"], "visitor", data.text)

    try:
        await telegram_bot.notify_chat_message(chat["id"], chat["visitor_name"], data.text)
    except telegram_bot.TelegramError as error:
        logger.warning("чат №%s: уведомление не отправлено: %s", chat["id"], error)

    return {"status": "ok"}


@router.get("/messages")
def get_messages(after: int = 0, x_chat_token: str | None = Header(default=None)):
    chat = _require_chat(x_chat_token)
    return {"messages": _public_messages(chat["id"], after)}

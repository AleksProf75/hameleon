"""Telegram: уведомления о заявках и чатах, кнопка «Беру», ответы менеджеров.

Бот получает нажатия кнопок и ответы через long polling (getUpdates),
поэтому на сервере не нужен отдельный адрес для webhook.
Опрос работает только в одном процессе: при HAMELEON_TELEGRAM_POLLING=0
он выключен (например, для тестового экземпляра API).
"""

import asyncio
import logging
import os

import httpx

import crm


logger = logging.getLogger("hameleon.telegram")

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

CHAT_IDS = [
    chat_id.strip()
    for chat_id in os.getenv(
        "TELEGRAM_CHAT_IDS",
        os.getenv("TELEGRAM_CHAT_ID", ""),
    ).split(",")
    if chat_id.strip()
]

POLLING_ENABLED = os.getenv("HAMELEON_TELEGRAM_POLLING", "1") != "0"

# Ответ менеджера посетителю чата не длиннее этого
MAX_REPLY_LENGTH = 2000


class TelegramError(Exception):
    pass


async def _call(client: httpx.AsyncClient, method: str, payload: dict, timeout: float = 10.0) -> dict:
    if not BOT_TOKEN:
        raise TelegramError("не задан TELEGRAM_BOT_TOKEN")

    response = await client.post(
        f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
        json=payload,
        timeout=timeout,
    )
    data = response.json()

    if not data.get("ok"):
        # Описание ошибки от Telegram не содержит токен
        raise TelegramError(f"{method}: {data.get('description', response.status_code)}")

    return data["result"]


async def broadcast(text: str, kind: str, ref_id: int, buttons: list | None = None) -> int:
    """Отправляет сообщение во все чаты менеджеров и запоминает его ID.

    Возвращает число чатов, куда сообщение дошло.
    """
    if not CHAT_IDS:
        raise TelegramError("не задан TELEGRAM_CHAT_IDS")

    delivered = 0

    async with httpx.AsyncClient() as client:
        for chat_id in CHAT_IDS:
            payload = {"chat_id": chat_id, "text": text}

            if buttons:
                payload["reply_markup"] = {"inline_keyboard": buttons}

            try:
                result = await _call(client, "sendMessage", payload)
                crm.remember_telegram_message(
                    result["chat"]["id"], result["message_id"], kind, ref_id
                )
                delivered += 1
            except (httpx.HTTPError, TelegramError) as error:
                logger.warning(
                    "%s #%s: не доставлено в один из чатов: %s",
                    kind,
                    ref_id,
                    error if isinstance(error, TelegramError) else type(error).__name__,
                )

    return delivered


def take_button(lead_id: int) -> list:
    return [[{"text": "✋ Беру", "callback_data": f"take:{lead_id}"}]]


async def notify_lead(lead_id: int, text: str) -> int:
    return await broadcast(f"№{lead_id}. {text}", "lead", lead_id, take_button(lead_id))


async def mark_lead_taken(lead_id: int, manager_name: str) -> None:
    """Заменяет кнопку «Беру» во всех чатах на «Взял: …»."""
    markup = {
        "inline_keyboard": [[{
            "text": f"✅ Взял(а): {manager_name}",
            "callback_data": f"taken:{lead_id}",
        }]]
    }

    async with httpx.AsyncClient() as client:
        for message in crm.telegram_messages_for("lead", lead_id):
            try:
                await _call(client, "editMessageReplyMarkup", {
                    "chat_id": message["tg_chat_id"],
                    "message_id": message["tg_message_id"],
                    "reply_markup": markup,
                })
            except (httpx.HTTPError, TelegramError):
                pass


async def notify_chat_message(chat_id: int, visitor_name: str | None, text: str) -> int:
    who = visitor_name or "Посетитель"
    return await broadcast(
        f"💬 Чат №{chat_id} — {who}:\n\n{text}\n\n"
        "↩️ Ответьте на это сообщение (Reply), чтобы написать посетителю.",
        "chat",
        chat_id,
    )


# ---------- Обработка нажатий и ответов ----------

async def _handle_callback(client: httpx.AsyncClient, callback: dict) -> None:
    data = callback.get("data", "")
    telegram_user_id = callback["from"]["id"]
    answer = "Готово"

    if data.startswith("take:"):
        lead_id = int(data.split(":", 1)[1])
        user = crm.user_by_telegram_id(telegram_user_id)

        if not user:
            answer = (
                "Вы не подключены к панели заявок. "
                f"Ваш Telegram ID: {telegram_user_id} — передайте его администратору."
            )
        else:
            taken, lead = crm.take_lead(lead_id, user)

            if taken:
                answer = f"Заявка №{lead_id} ваша"
                await mark_lead_taken(lead_id, user["display_name"])
            elif lead:
                answer = f"Заявку уже взял(а): {lead['assigned_name']}"
            else:
                answer = "Заявка не найдена"

    elif data.startswith("taken:"):
        lead = crm.get_lead(int(data.split(":", 1)[1]))
        answer = f"Заявку взял(а): {lead['assigned_name']}" if lead else ""

    await _call(client, "answerCallbackQuery", {
        "callback_query_id": callback["id"],
        "text": answer,
        "show_alert": answer.startswith("Вы не подключены"),
    })


async def _reply(client: httpx.AsyncClient, message: dict, text: str) -> None:
    await _call(client, "sendMessage", {
        "chat_id": message["chat"]["id"],
        "text": text,
        "reply_to_message_id": message["message_id"],
    })


async def _handle_message(client: httpx.AsyncClient, message: dict) -> None:
    text = (message.get("text") or "").strip()
    sender = message.get("from") or {}

    if text.startswith("/myid"):
        await _reply(client, message, f"Ваш Telegram ID: {sender.get('id')}")
        return

    original = message.get("reply_to_message")

    if not text or not original:
        return

    target = crm.find_by_telegram_message(message["chat"]["id"], original["message_id"])

    if not target:
        return

    user = crm.user_by_telegram_id(sender.get("id"))

    if not user:
        await _reply(
            client,
            message,
            "Вы не подключены к панели заявок, ответ не сохранён. "
            f"Ваш Telegram ID: {sender.get('id')} — передайте его администратору.",
        )
        return

    if target["kind"] == "lead":
        crm.add_comment(target["ref_id"], user["id"], text[:MAX_REPLY_LENGTH], via="telegram")
        await _reply(client, message, f"Комментарий к заявке №{target['ref_id']} сохранён")

    elif target["kind"] == "chat":
        crm.add_chat_message(target["ref_id"], "manager", text[:MAX_REPLY_LENGTH], user["id"])

        # Новое сообщение тоже связываем с чатом, чтобы на него можно было ответить
        crm.remember_telegram_message(
            message["chat"]["id"], message["message_id"], "chat", target["ref_id"]
        )
        await _reply(client, message, f"Отправлено посетителю (чат №{target['ref_id']})")


async def polling_loop() -> None:
    if not BOT_TOKEN or not POLLING_ENABLED:
        logger.info("опрос Telegram выключен")
        return

    offset = 0
    logger.info("опрос Telegram запущен")

    async with httpx.AsyncClient() as client:
        while True:
            try:
                updates = await _call(client, "getUpdates", {
                    "offset": offset,
                    "timeout": 25,
                    "allowed_updates": ["message", "callback_query"],
                }, timeout=35.0)

                for update in updates:
                    offset = update["update_id"] + 1

                    try:
                        if "callback_query" in update:
                            await _handle_callback(client, update["callback_query"])
                        elif "message" in update:
                            await _handle_message(client, update["message"])
                    except Exception as error:
                        # Текст ошибок httpx может содержать URL с токеном бота
                        logger.error(
                            "ошибка обработки сообщения Telegram: %s",
                            type(error).__name__
                            if isinstance(error, httpx.HTTPError) else repr(error),
                        )

            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning(
                    "опрос Telegram: %s",
                    error if isinstance(error, TelegramError) else type(error).__name__,
                )
                await asyncio.sleep(5)

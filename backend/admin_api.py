"""API панели заявок для менеджеров и администратора: /api/admin/..."""

import logging
import os
import sqlite3
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

import auth
import crm
import db
import telegram_bot


logger = logging.getLogger("hameleon.admin")

router = APIRouter(prefix="/api/admin")

PANEL_HTML = os.path.join(os.path.dirname(__file__), "panel", "index.html")


class StrictModel(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class LoginRequest(StrictModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=200)


class CommentRequest(StrictModel):
    text: str = Field(min_length=1, max_length=2000)


class StatusRequest(StrictModel):
    status: Literal["new", "in_work", "done", "rejected"]


class AssignRequest(StrictModel):
    user_id: int | None


class ChatStatusRequest(StrictModel):
    status: Literal["open", "closed"]


class UserCreate(StrictModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    display_name: str = Field(min_length=1, max_length=100)
    password: str = Field(max_length=200)
    role: Literal["admin", "manager"] = "manager"
    telegram_user_id: int | None = None


class UserUpdate(StrictModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    password: str | None = Field(default=None, max_length=200)
    role: Literal["admin", "manager"] | None = None
    telegram_user_id: int | None = None
    clear_telegram: bool = False
    active: bool | None = None


class PasswordChange(StrictModel):
    old_password: str = Field(max_length=200)
    new_password: str = Field(max_length=200)


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "username": user["username"],
        "display_name": user["display_name"],
        "role": user["role"],
    }


def _lead_view(lead: dict) -> dict:
    lead = dict(lead)
    lead["created_local"] = crm.local_time(lead["created_at"])
    lead["taken_local"] = crm.local_time(lead["taken_at"])
    lead["closed_local"] = crm.local_time(lead["closed_at"])
    lead["status_label"] = crm.STATUS_LABELS[lead["status"]]
    return lead


def _require_lead(lead_id: int) -> dict:
    lead = crm.get_lead(lead_id)

    if not lead:
        raise HTTPException(status_code=404, detail="Заявка не найдена")

    return lead


# ---------- Страница панели и вход ----------

@router.get("/", include_in_schema=False)
def panel_page():
    return FileResponse(
        PANEL_HTML,
        headers={
            "Cache-Control": "no-store",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "no-referrer",
            "Content-Security-Policy": (
                "default-src 'self'; script-src 'self' 'unsafe-inline';"
                " style-src 'self' 'unsafe-inline'; frame-ancestors 'none'"
            ),
        },
    )


@router.post("/login")
def login(data: LoginRequest, request: Request, response: Response):
    ip = request.client.host if request.client else "unknown"
    username = data.username.lower()

    if auth.login_blocked(ip, username):
        raise HTTPException(
            status_code=429,
            detail="Слишком много попыток входа. Попробуйте через 15 минут.",
        )

    user = db.query_one(
        "SELECT * FROM users WHERE username = ? AND active = 1", (username,)
    )

    if not user or not auth.verify_password(data.password, user["password_hash"]):
        auth.register_failure(ip, username)
        logger.warning("неудачный вход: логин=%s", username)
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    token, csrf_token = auth.create_session(user["id"])
    auth.set_session_cookie(response, token)
    logger.info("вход в панель: логин=%s", username)

    return {"user": _public_user(user), "csrf_token": csrf_token}


@router.post("/logout")
def logout(request: Request, response: Response, user: dict = Depends(auth.current_user)):
    auth.delete_session(request.cookies.get(auth.SESSION_COOKIE, ""))
    response.delete_cookie(auth.SESSION_COOKIE, path="/")
    return {"status": "ok"}


@router.get("/me")
def me(user: dict = Depends(auth.current_user)):
    return {"user": _public_user(user), "csrf_token": user["csrf_token"]}


@router.post("/me/password")
def change_own_password(data: PasswordChange, user: dict = Depends(auth.current_user)):
    row = db.query_one("SELECT password_hash FROM users WHERE id = ?", (user["id"],))

    if not auth.verify_password(data.old_password, row["password_hash"]):
        raise HTTPException(status_code=400, detail="Текущий пароль неверный")

    auth.validate_new_password(data.new_password)

    with db.transaction() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (auth.hash_password(data.new_password), user["id"]),
        )

    return {"status": "ok"}


# ---------- Заявки ----------

@router.get("/leads")
def leads(
    status: Literal["new", "in_work", "done", "rejected"] | None = None,
    mine: bool = False,
    limit: int = 200,
    user: dict = Depends(auth.current_user),
):
    rows = crm.list_leads(status, user["id"] if mine else None, min(limit, 1000))
    return [_lead_view(row) for row in rows]


@router.get("/leads/{lead_id}")
def lead_detail(lead_id: int, user: dict = Depends(auth.current_user)):
    lead = _require_lead(lead_id)
    events = [
        {**event, "created_local": crm.local_time(event["created_at"])}
        for event in crm.lead_events(lead_id)
    ]
    return {"lead": _lead_view(lead), "events": events}


@router.post("/leads/{lead_id}/take")
async def take(lead_id: int, user: dict = Depends(auth.current_user)):
    _require_lead(lead_id)
    taken, lead = crm.take_lead(lead_id, user)

    if not taken:
        raise HTTPException(
            status_code=409,
            detail=f"Заявку уже взял(а): {lead['assigned_name']}",
        )

    await telegram_bot.mark_lead_taken(lead_id, user["display_name"])
    return {"status": "ok"}


@router.post("/leads/{lead_id}/comment")
def comment(lead_id: int, data: CommentRequest, user: dict = Depends(auth.current_user)):
    _require_lead(lead_id)
    crm.add_comment(lead_id, user["id"], data.text)
    return {"status": "ok"}


@router.post("/leads/{lead_id}/status")
def change_status(lead_id: int, data: StatusRequest, user: dict = Depends(auth.current_user)):
    lead = _require_lead(lead_id)

    if (
        user["role"] != "admin"
        and lead["assigned_user_id"] not in (None, user["id"])
    ):
        raise HTTPException(
            status_code=403,
            detail="Менять статус может только тот, кто взял заявку, или администратор",
        )

    crm.set_status(lead_id, data.status, user)
    return {"status": "ok"}


@router.post("/leads/{lead_id}/assign")
async def assign(lead_id: int, data: AssignRequest, admin: dict = Depends(auth.require_admin)):
    _require_lead(lead_id)
    target = None

    if data.user_id is not None:
        target = db.query_one(
            "SELECT display_name FROM users WHERE id = ? AND active = 1",
            (data.user_id,),
        )

        if not target:
            raise HTTPException(status_code=400, detail="Пользователь не найден")

    crm.assign_lead(lead_id, data.user_id, admin)

    if target:
        await telegram_bot.mark_lead_taken(lead_id, target["display_name"])

    return {"status": "ok"}


# ---------- Чаты ----------

@router.get("/chats")
def chats(user: dict = Depends(auth.current_user)):
    return [
        {**chat, "last_local": crm.local_time(chat["last_message_at"])}
        for chat in crm.list_chats(200)
    ]


@router.get("/chats/{chat_id}/messages")
def chat_detail(chat_id: int, user: dict = Depends(auth.current_user)):
    return [
        {**message, "created_local": crm.local_time(message["created_at"])}
        for message in crm.chat_messages(chat_id)
    ]


@router.post("/chats/{chat_id}/reply")
def chat_reply(chat_id: int, data: CommentRequest, user: dict = Depends(auth.current_user)):
    if not db.query_one("SELECT id FROM chats WHERE id = ?", (chat_id,)):
        raise HTTPException(status_code=404, detail="Чат не найден")

    crm.add_chat_message(chat_id, "manager", data.text, user["id"])
    return {"status": "ok"}


@router.post("/chats/{chat_id}/status")
def chat_status(chat_id: int, data: ChatStatusRequest, user: dict = Depends(auth.current_user)):
    crm.set_chat_status(chat_id, data.status)
    return {"status": "ok"}


# ---------- Пользователи (только администратор) ----------

@router.get("/users")
def users(admin: dict = Depends(auth.require_admin)):
    return db.query(
        "SELECT id, username, display_name, role, telegram_user_id, active, created_at"
        " FROM users ORDER BY active DESC, display_name"
    )


@router.post("/users")
def create_user(data: UserCreate, admin: dict = Depends(auth.require_admin)):
    auth.validate_new_password(data.password)

    try:
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO users (username, display_name, password_hash, role,"
                " telegram_user_id, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    data.username.lower(),
                    data.display_name,
                    auth.hash_password(data.password),
                    data.role,
                    data.telegram_user_id,
                    db.now(),
                ),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=400,
            detail="Такой логин или Telegram ID уже используется",
        )

    logger.info("создан пользователь: логин=%s роль=%s", data.username.lower(), data.role)
    return {"status": "ok"}


@router.patch("/users/{user_id}")
def update_user(user_id: int, data: UserUpdate, admin: dict = Depends(auth.require_admin)):
    target = db.query_one("SELECT id FROM users WHERE id = ?", (user_id,))

    if not target:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if user_id == admin["id"] and (data.active is False or data.role == "manager"):
        raise HTTPException(
            status_code=400,
            detail="Нельзя отключить себя или снять с себя права администратора",
        )

    fields = {}

    if data.display_name is not None:
        fields["display_name"] = data.display_name

    if data.role is not None:
        fields["role"] = data.role

    if data.active is not None:
        fields["active"] = int(data.active)

    if data.clear_telegram:
        fields["telegram_user_id"] = None
    elif data.telegram_user_id is not None:
        fields["telegram_user_id"] = data.telegram_user_id

    if data.password:
        auth.validate_new_password(data.password)
        fields["password_hash"] = auth.hash_password(data.password)

    if not fields:
        return {"status": "ok"}

    try:
        with db.transaction() as conn:
            conn.execute(
                "UPDATE users SET " + ", ".join(f"{name} = ?" for name in fields)
                + " WHERE id = ?",
                (*fields.values(), user_id),
            )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="Этот Telegram ID уже используется")

    # После смены пароля, роли или отключения — выйти со всех устройств
    if data.password or data.active is False or data.role:
        auth.delete_user_sessions(user_id)

    return {"status": "ok"}

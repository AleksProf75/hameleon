"""Вход в панель: пароли, сессии, роли и защита от подбора пароля."""

import hashlib
import hmac
import os
import secrets
import time
from collections import deque
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request

import db


SESSION_COOKIE = "hameleon_session"
SESSION_DAYS = 14
COOKIE_SECURE = os.getenv("HAMELEON_COOKIE_SECURE", "1") != "0"

# Не больше 5 неудачных входов за 15 минут с одного адреса или на один логин
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_MAX_FAILURES = 5

_failures: dict[str, deque] = {}


# ---------- Пароли ----------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32
    )
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False

    digest = hashlib.scrypt(
        password.encode(),
        salt=bytes.fromhex(salt_hex),
        n=2**14,
        r=8,
        p=1,
        dklen=32,
    )
    return hmac.compare_digest(digest.hex(), digest_hex)


def validate_new_password(password: str) -> None:
    if len(password) < 10:
        raise HTTPException(
            status_code=400,
            detail="Пароль должен быть не короче 10 символов",
        )


# ---------- Защита от подбора ----------

def _recent(key: str) -> deque:
    now = time.monotonic()
    attempts = _failures.setdefault(key, deque())

    while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
        attempts.popleft()

    return attempts


def login_blocked(ip: str, username: str) -> bool:
    return (
        len(_recent(f"ip:{ip}")) >= LOGIN_MAX_FAILURES
        or len(_recent(f"user:{username}")) >= LOGIN_MAX_FAILURES
    )


def register_failure(ip: str, username: str) -> None:
    now = time.monotonic()
    _recent(f"ip:{ip}").append(now)
    _recent(f"user:{username}").append(now)


# ---------- Сессии ----------

def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(user_id: int) -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)

    with db.transaction() as conn:
        conn.execute(
            "DELETE FROM sessions WHERE expires_at < ?", (db.now(),)
        )
        conn.execute(
            "INSERT INTO sessions (token_hash, user_id, csrf_token,"
            " created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
            (
                _token_hash(token),
                user_id,
                csrf_token,
                db.now(),
                expires.isoformat(timespec="seconds"),
            ),
        )

    return token, csrf_token


def delete_session(token: str) -> None:
    with db.transaction() as conn:
        conn.execute(
            "DELETE FROM sessions WHERE token_hash = ?", (_token_hash(token),)
        )


def delete_user_sessions(user_id: int) -> None:
    with db.transaction() as conn:
        conn.execute("DELETE FROM sessions WHERE user_id = ?", (user_id,))


def set_session_cookie(response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,
        secure=COOKIE_SECURE,
        samesite="strict",
        path="/",
    )


def current_user(request: Request) -> dict:
    """Пользователь по cookie. Для изменяющих запросов проверяет CSRF-токен."""
    token = request.cookies.get(SESSION_COOKIE)

    if not token:
        raise HTTPException(status_code=401, detail="Требуется вход")

    row = db.query_one(
        "SELECT s.csrf_token, s.expires_at, u.id, u.username,"
        " u.display_name, u.role, u.telegram_user_id, u.active"
        " FROM sessions s JOIN users u ON u.id = s.user_id"
        " WHERE s.token_hash = ?",
        (_token_hash(token),),
    )

    if not row or not row["active"] or row["expires_at"] < db.now():
        raise HTTPException(status_code=401, detail="Требуется вход")

    if request.method not in ("GET", "HEAD", "OPTIONS"):
        sent = request.headers.get("X-CSRF-Token", "")

        if not hmac.compare_digest(sent, row["csrf_token"]):
            raise HTTPException(status_code=403, detail="Неверный CSRF-токен")

    return row


def require_admin(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    return user

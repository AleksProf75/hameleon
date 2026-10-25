"""Хранилище заявок, пользователей панели и чатов (SQLite)."""

import os
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone


DB_PATH = os.getenv(
    "HAMELEON_DB",
    os.path.join(os.path.dirname(__file__), "data", "hameleon.db"),
)

_lock = threading.Lock()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'manager')),
    telegram_user_id INTEGER UNIQUE,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    csrf_token TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS leads (
    id INTEGER PRIMARY KEY,
    created_at TEXT NOT NULL,
    source TEXT NOT NULL,
    name TEXT NOT NULL,
    phone TEXT NOT NULL,
    promotion TEXT,
    details TEXT,
    status TEXT NOT NULL DEFAULT 'new'
        CHECK (status IN ('new', 'in_work', 'done', 'rejected')),
    assigned_user_id INTEGER REFERENCES users(id),
    taken_at TEXT,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS lead_events (
    id INTEGER PRIMARY KEY,
    lead_id INTEGER NOT NULL REFERENCES leads(id),
    created_at TEXT NOT NULL,
    user_id INTEGER REFERENCES users(id),
    kind TEXT NOT NULL,
    text TEXT
);

CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY,
    token_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    last_message_at TEXT NOT NULL,
    visitor_name TEXT,
    status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
    assigned_user_id INTEGER REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY,
    chat_id INTEGER NOT NULL REFERENCES chats(id),
    created_at TEXT NOT NULL,
    author TEXT NOT NULL CHECK (author IN ('visitor', 'manager')),
    user_id INTEGER REFERENCES users(id),
    text TEXT NOT NULL
);

-- Какому сообщению в Telegram соответствует заявка или чат:
-- нужно, чтобы понять, на что ответил менеджер
CREATE TABLE IF NOT EXISTS telegram_messages (
    tg_chat_id INTEGER NOT NULL,
    tg_message_id INTEGER NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('lead', 'chat')),
    ref_id INTEGER NOT NULL,
    PRIMARY KEY (tg_chat_id, tg_message_id)
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by INTEGER REFERENCES users(id)
);

CREATE INDEX IF NOT EXISTS idx_leads_created ON leads(created_at);
CREATE INDEX IF NOT EXISTS idx_lead_events_lead ON lead_events(lead_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_chat ON chat_messages(chat_id);
CREATE INDEX IF NOT EXISTS idx_tg_ref ON telegram_messages(kind, ref_id);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

    with _connect() as conn:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.executescript(SCHEMA)


@contextmanager
def transaction():
    """Одна транзакция; запись идёт последовательно из всех потоков."""
    with _lock:
        conn = _connect()

        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def query(sql: str, params: tuple = ()) -> list[dict]:
    conn = _connect()

    try:
        return [dict(row) for row in conn.execute(sql, params)]
    finally:
        conn.close()


def query_one(sql: str, params: tuple = ()) -> dict | None:
    rows = query(sql, params)
    return rows[0] if rows else None

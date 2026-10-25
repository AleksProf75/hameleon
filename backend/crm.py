"""Операции с заявками и чатами: создание, «взять в работу», комментарии."""

import hashlib
import json
import secrets
from datetime import datetime
from zoneinfo import ZoneInfo

import db


TZ = ZoneInfo("Europe/Moscow")

STATUS_LABELS = {
    "new": "Новая",
    "in_work": "В работе",
    "done": "Выполнена",
    "rejected": "Отказ",
}


def local_time(iso: str | None) -> str:
    if not iso:
        return ""

    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%d.%m.%Y %H:%M")


# ---------- Заявки ----------

def create_lead(
    source: str,
    name: str,
    phone: str,
    promotion: str | None,
    details: dict | None,
) -> int:
    with db.transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO leads (created_at, source, name, phone, promotion, details)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                db.now(),
                source,
                name,
                phone,
                promotion,
                json.dumps(details, ensure_ascii=False) if details else None,
            ),
        )
        lead_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO lead_events (lead_id, created_at, kind, text)"
            " VALUES (?, ?, 'created', ?)",
            (lead_id, db.now(), "Заявка получена с сайта"),
        )

    return lead_id


def take_lead(lead_id: int, user: dict) -> tuple[bool, dict | None]:
    """Назначает заявку менеджеру, если её ещё никто не взял.

    Возвращает (успех, заявка). Если заявку уже взял другой,
    успех False, а в заявке указан тот, кто взял.
    """
    with db.transaction() as conn:
        updated = conn.execute(
            "UPDATE leads SET assigned_user_id = ?, taken_at = ?, status = 'in_work'"
            " WHERE id = ? AND assigned_user_id IS NULL",
            (user["id"], db.now(), lead_id),
        ).rowcount

        if updated:
            conn.execute(
                "INSERT INTO lead_events (lead_id, created_at, user_id, kind, text)"
                " VALUES (?, ?, ?, 'taken', ?)",
                (lead_id, db.now(), user["id"], "Взял(а) заявку в работу"),
            )

    return bool(updated), get_lead(lead_id)


def assign_lead(lead_id: int, user_id: int | None, by_user: dict) -> None:
    """Переназначение заявки администратором."""
    target = db.query_one(
        "SELECT display_name FROM users WHERE id = ?", (user_id,)
    ) if user_id else None

    with db.transaction() as conn:
        conn.execute(
            "UPDATE leads SET assigned_user_id = ?,"
            " taken_at = CASE WHEN ? IS NULL THEN NULL ELSE ? END,"
            " status = CASE WHEN ? IS NULL THEN 'new' ELSE"
            "   CASE WHEN status = 'new' THEN 'in_work' ELSE status END END"
            " WHERE id = ?",
            (user_id, user_id, db.now(), user_id, lead_id),
        )
        conn.execute(
            "INSERT INTO lead_events (lead_id, created_at, user_id, kind, text)"
            " VALUES (?, ?, ?, 'assigned', ?)",
            (
                lead_id,
                db.now(),
                by_user["id"],
                f"Назначено: {target['display_name']}" if target
                else "Назначение снято",
            ),
        )


def add_comment(lead_id: int, user_id: int, text: str, via: str = "panel") -> None:
    prefix = "Telegram: " if via == "telegram" else ""

    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO lead_events (lead_id, created_at, user_id, kind, text)"
            " VALUES (?, ?, ?, 'comment', ?)",
            (lead_id, db.now(), user_id, prefix + text),
        )


def set_status(lead_id: int, status: str, user: dict) -> None:
    closed = status in ("done", "rejected")

    with db.transaction() as conn:
        conn.execute(
            "UPDATE leads SET status = ?, closed_at = ?,"
            " assigned_user_id = COALESCE(assigned_user_id, ?),"
            " taken_at = COALESCE(taken_at, ?)"
            " WHERE id = ?",
            (
                status,
                db.now() if closed else None,
                user["id"],
                db.now(),
                lead_id,
            ),
        )
        conn.execute(
            "INSERT INTO lead_events (lead_id, created_at, user_id, kind, text)"
            " VALUES (?, ?, ?, 'status', ?)",
            (lead_id, db.now(), user["id"], f"Статус: {STATUS_LABELS[status]}"),
        )


LEAD_SELECT = (
    "SELECT l.*, u.display_name AS assigned_name FROM leads l"
    " LEFT JOIN users u ON u.id = l.assigned_user_id"
)


def get_lead(lead_id: int) -> dict | None:
    lead = db.query_one(LEAD_SELECT + " WHERE l.id = ?", (lead_id,))

    if lead and lead["details"]:
        lead["details"] = json.loads(lead["details"])

    return lead


def list_leads(status: str | None, assigned_user_id: int | None, limit: int) -> list[dict]:
    where = []
    params: list = []

    if status:
        where.append("l.status = ?")
        params.append(status)

    if assigned_user_id:
        where.append("l.assigned_user_id = ?")
        params.append(assigned_user_id)

    sql = LEAD_SELECT

    if where:
        sql += " WHERE " + " AND ".join(where)

    sql += " ORDER BY l.id DESC LIMIT ?"
    params.append(limit)

    return db.query(sql, tuple(params))


def lead_events(lead_id: int) -> list[dict]:
    return db.query(
        "SELECT e.*, u.display_name AS user_name FROM lead_events e"
        " LEFT JOIN users u ON u.id = e.user_id"
        " WHERE e.lead_id = ? ORDER BY e.id",
        (lead_id,),
    )


# ---------- Чаты ----------

def _chat_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_chat(visitor_name: str | None) -> tuple[int, str]:
    token = secrets.token_urlsafe(24)

    with db.transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO chats (token_hash, created_at, last_message_at, visitor_name)"
            " VALUES (?, ?, ?, ?)",
            (_chat_token_hash(token), db.now(), db.now(), visitor_name),
        )

    return cursor.lastrowid, token


def chat_by_token(token: str) -> dict | None:
    return db.query_one(
        "SELECT * FROM chats WHERE token_hash = ?", (_chat_token_hash(token),)
    )


def add_chat_message(
    chat_id: int, author: str, text: str, user_id: int | None = None
) -> int:
    with db.transaction() as conn:
        cursor = conn.execute(
            "INSERT INTO chat_messages (chat_id, created_at, author, user_id, text)"
            " VALUES (?, ?, ?, ?, ?)",
            (chat_id, db.now(), author, user_id, text),
        )
        conn.execute(
            "UPDATE chats SET last_message_at = ?, status = 'open',"
            " assigned_user_id = COALESCE(assigned_user_id, ?) WHERE id = ?",
            (db.now(), user_id, chat_id),
        )

    return cursor.lastrowid


def chat_messages(chat_id: int, after_id: int = 0) -> list[dict]:
    return db.query(
        "SELECT m.id, m.created_at, m.author, m.text, u.display_name AS user_name"
        " FROM chat_messages m LEFT JOIN users u ON u.id = m.user_id"
        " WHERE m.chat_id = ? AND m.id > ? ORDER BY m.id",
        (chat_id, after_id),
    )


def list_chats(limit: int) -> list[dict]:
    return db.query(
        "SELECT c.id, c.created_at, c.last_message_at, c.visitor_name, c.status,"
        " u.display_name AS assigned_name,"
        " (SELECT text FROM chat_messages WHERE chat_id = c.id"
        "   ORDER BY id DESC LIMIT 1) AS last_text,"
        " (SELECT author FROM chat_messages WHERE chat_id = c.id"
        "   ORDER BY id DESC LIMIT 1) AS last_author"
        " FROM chats c LEFT JOIN users u ON u.id = c.assigned_user_id"
        " ORDER BY c.last_message_at DESC LIMIT ?",
        (limit,),
    )


def set_chat_status(chat_id: int, status: str) -> None:
    with db.transaction() as conn:
        conn.execute("UPDATE chats SET status = ? WHERE id = ?", (status, chat_id))


# ---------- Связь с сообщениями Telegram ----------

def remember_telegram_message(
    tg_chat_id: int, tg_message_id: int, kind: str, ref_id: int
) -> None:
    with db.transaction() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO telegram_messages"
            " (tg_chat_id, tg_message_id, kind, ref_id) VALUES (?, ?, ?, ?)",
            (tg_chat_id, tg_message_id, kind, ref_id),
        )


def telegram_messages_for(kind: str, ref_id: int) -> list[dict]:
    return db.query(
        "SELECT tg_chat_id, tg_message_id FROM telegram_messages"
        " WHERE kind = ? AND ref_id = ?",
        (kind, ref_id),
    )


def find_by_telegram_message(tg_chat_id: int, tg_message_id: int) -> dict | None:
    return db.query_one(
        "SELECT kind, ref_id FROM telegram_messages"
        " WHERE tg_chat_id = ? AND tg_message_id = ?",
        (tg_chat_id, tg_message_id),
    )


def user_by_telegram_id(telegram_user_id: int) -> dict | None:
    return db.query_one(
        "SELECT id, username, display_name, role FROM users"
        " WHERE telegram_user_id = ? AND active = 1",
        (telegram_user_id,),
    )

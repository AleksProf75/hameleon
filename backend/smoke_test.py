"""Проверка API без Telegram и без настоящей базы.

Запуск из папки backend:  python smoke_test.py
"""

import os
import sys
import tempfile

# Настройки задаём до импорта приложения
_tmp = tempfile.mkdtemp()
os.environ["HAMELEON_DB"] = os.path.join(_tmp, "test.db")
os.environ["HAMELEON_COOKIE_SECURE"] = "0"
os.environ["HAMELEON_TELEGRAM_POLLING"] = "0"
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_IDS"] = ""

from fastapi.testclient import TestClient  # noqa: E402

import auth  # noqa: E402
import db  # noqa: E402
import main  # noqa: E402


def check(condition: bool, message: str) -> None:
    if not condition:
        sys.exit(f"ОШИБКА: {message}")

    print(f"ok  {message}")


def add_user(username: str, role: str) -> None:
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO users (username, display_name, password_hash, role, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (username, username.title(), auth.hash_password("password-123"), role, db.now()),
        )


def login(client: TestClient, username: str) -> dict:
    response = client.post("/api/admin/login", json={
        "username": username, "password": "password-123",
    })
    check(response.status_code == 200, f"вход {username}")
    return {"X-CSRF-Token": response.json()["csrf_token"]}


LEAD = {
    "name": "Иван",
    "phone": "+7 (999) 123-45-67",
    "source": "calculator",
    "calculator": {
        "width": 4.2, "length": 5, "ceiling_type": "Матовый",
        "corners": 4, "lights": 6,
    },
    "promotion_id": "svo_discount_10",
    "form_elapsed_ms": 5000,
}


with TestClient(main.app) as client:
    # --- Заявка с сайта ---
    response = client.post("/api/leads", json=LEAD)
    check(response.status_code == 200, "заявка принята и сохранена без Telegram")

    check(client.post("/api/leads", json={**LEAD, "phone": "abc"}).status_code == 422,
          "неверный телефон отклонён")
    check(client.post("/api/leads", json={**LEAD, "promotion_id": "fake"}).status_code == 422,
          "неизвестная акция отклонена")
    check(client.post("/api/leads", json={**LEAD, "form_elapsed_ms": 100}).status_code == 400,
          "слишком быстрое заполнение отклонено")
    check(client.get("/docs").status_code == 404, "документация API скрыта")

    # --- Доступ без входа ---
    check(client.get("/api/admin/leads").status_code == 401, "без входа заявки не видны")
    check(client.get("/api/admin/").status_code == 200, "страница панели открывается")

    add_user("admin", "admin")
    add_user("anna", "manager")
    add_user("boris", "manager")

    bad = client.post("/api/admin/login", json={"username": "anna", "password": "wrong"})
    check(bad.status_code == 401, "неверный пароль не пускает")

    # --- Менеджер Анна ---
    anna = login(client, "anna")
    leads = client.get("/api/admin/leads").json()
    check(len(leads) == 1, "менеджер видит заявку")

    counts = client.get("/api/admin/summary").json()
    check(counts["new_leads"] == 1 and counts["last_lead_id"] == leads[0]["id"],
          "сводка показывает новую заявку")
    lead_id = leads[0]["id"]

    detail = client.get(f"/api/admin/leads/{lead_id}").json()
    check(detail["lead"]["details"]["Стоимость, ₽"] == 11900, "цена посчитана сервером")
    check("СВО" in detail["lead"]["promotion"], "акция взята из списка сервера")

    check(client.post(f"/api/admin/leads/{lead_id}/take").status_code == 403,
          "без CSRF-токена действие запрещено")
    check(client.post(f"/api/admin/leads/{lead_id}/take", headers=anna).status_code == 200,
          "менеджер взял заявку")
    check(client.post(f"/api/admin/leads/{lead_id}/comment", headers=anna,
                      json={"text": "Позвонила, замер в пятницу"}).status_code == 200,
          "комментарий добавлен")
    check(client.get("/api/admin/users").status_code == 403, "менеджеру список пользователей закрыт")

    # --- Менеджер Борис не может перехватить чужую заявку ---
    boris = login(client, "boris")
    check(client.post(f"/api/admin/leads/{lead_id}/take", headers=boris).status_code == 409,
          "вторая попытка взять заявку отклонена")
    check(client.post(f"/api/admin/leads/{lead_id}/status", headers=boris,
                      json={"status": "done"}).status_code == 403,
          "чужую заявку закрыть нельзя")

    # --- Администратор ---
    admin = login(client, "admin")
    check(client.post(f"/api/admin/leads/{lead_id}/status", headers=admin,
                      json={"status": "done"}).status_code == 200,
          "администратор закрыл заявку")
    events = client.get(f"/api/admin/leads/{lead_id}").json()["events"]
    check([e["kind"] for e in events] == ["created", "taken", "comment", "status"],
          "история заявки записана по порядку")
    check(client.post("/api/admin/users", headers=admin, json={
        "username": "vera", "display_name": "Вера", "password": "short",
    }).status_code == 400, "короткий пароль не принят")
    check(client.post("/api/admin/users", headers=admin, json={
        "username": "vera", "display_name": "Вера", "password": "long-password-1",
    }).status_code == 200, "администратор создал менеджера")

    # --- Настройки сайта ---
    check(client.get("/api/site/settings").json()["hero"]["value"] == "20%",
          "сайт получает настройки по умолчанию")

    settings = client.get("/api/admin/settings").json()
    settings["calculator"]["types"] = [{"name": "Матовый", "price_per_m2": 1000}]
    settings["promotions"].append({
        "value": "5%", "title": "Новая акция", "text": "", "button": "Хочу",
    })
    saved = client.put("/api/admin/settings", headers=admin, json=settings)
    check(saved.status_code == 200, "администратор сохранил акции и цены")
    new_promo_id = saved.json()["promotions"][-1]["id"]
    check(new_promo_id.startswith("promo_"), "новой акции присвоен ID")

    check(client.get("/api/site/settings").json()["calculator"]["types"][0]["price_per_m2"] == 1000,
          "сайт видит новые цены")

    bad = {**settings, "price_cards": settings["price_cards"][:2]}
    check(client.put("/api/admin/settings", headers=admin, json=bad).status_code == 422,
          "неполный прайс не сохраняется")

    lead = {**LEAD, "promotion_id": new_promo_id, "phone": "+7 999 000-00-01"}
    check(client.post("/api/leads", json=lead).status_code == 200, "заявка с новой акцией принята")
    check(client.post("/api/leads", json={
        **LEAD, "calculator": {**LEAD["calculator"], "ceiling_type": "Глянцевый"},
    }).status_code == 422, "удалённый тип потолка отклонён")

    newest = client.get("/api/admin/leads").json()[0]
    detail = client.get(f"/api/admin/leads/{newest['id']}").json()["lead"]
    check(detail["details"]["Стоимость, ₽"] == 23400 and "Новая акция" in detail["promotion"],
          "цена и акция в заявке взяты из новых настроек")

    boris = login(client, "boris")
    check(client.get("/api/admin/settings").status_code == 403, "менеджеру настройки закрыты")
    admin = login(client, "admin")

    # --- Чат ---
    client.cookies.clear()
    started = client.post("/api/chat/start", json={"name": "Ольга", "text": "Сколько стоит?"})
    check(started.status_code == 200, "посетитель начал чат")
    token = started.json()["token"]

    check(client.get("/api/chat/messages", headers={"X-Chat-Token": "wrong"}).status_code == 404,
          "чужой чат не читается")

    admin = login(client, "admin")
    chat_id = client.get("/api/admin/chats").json()[0]["id"]
    check(client.get("/api/admin/summary").json()["waiting_chats"] == 1,
          "сводка показывает чат, ждущий ответа")
    check(client.post(f"/api/admin/chats/{chat_id}/reply", headers=admin,
                      json={"text": "От 450 ₽ за м²"}).status_code == 200,
          "менеджер ответил в чат")

    messages = client.get("/api/chat/messages", headers={"X-Chat-Token": token}).json()["messages"]
    check(messages[-1]["author"] == "manager" and messages[-1]["manager"] == "Admin",
          "посетитель видит ответ менеджера")

    # --- Подбор пароля ---
    for _ in range(5):
        client.post("/api/admin/login", json={"username": "boris", "password": "wrong"})
    check(client.post("/api/admin/login", json={
        "username": "boris", "password": "password-123",
    }).status_code == 429, "после 5 ошибок вход временно заблокирован")

print("Все проверки пройдены")

"""Служебные команды на сервере.

Создать администратора (пароль спросит без вывода на экран):
    python manage.py create-admin ЛОГИН "Имя Фамилия"
"""

import getpass
import sqlite3
import sys

from dotenv import load_dotenv

load_dotenv()

import auth  # noqa: E402
import db  # noqa: E402


def create_admin(username: str, display_name: str) -> None:
    password = getpass.getpass("Пароль (не короче 10 символов): ")

    if len(password) < 10:
        sys.exit("Пароль слишком короткий")

    if password != getpass.getpass("Повторите пароль: "):
        sys.exit("Пароли не совпадают")

    db.init_db()

    try:
        with db.transaction() as conn:
            conn.execute(
                "INSERT INTO users (username, display_name, password_hash, role, created_at)"
                " VALUES (?, ?, ?, 'admin', ?)",
                (username.lower(), display_name, auth.hash_password(password), db.now()),
            )
    except sqlite3.IntegrityError:
        sys.exit("Такой логин уже существует")

    print(f"Администратор {username.lower()} создан")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "create-admin":
        create_admin(sys.argv[2], sys.argv[3])
    else:
        sys.exit(__doc__)

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def mask_database_url(database_url: str) -> str:
    parsed = urlsplit(database_url)
    if parsed.scheme.startswith("sqlite"):
        return database_url
    if "@" not in parsed.netloc:
        return database_url

    userinfo, hostinfo = parsed.netloc.rsplit("@", 1)
    if ":" in userinfo:
        username, _password = userinfo.split(":", 1)
        userinfo = f"{username}:***"
    netloc = f"{userinfo}@{hostinfo}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def build_alembic_config(database_url: str) -> Config:
    from app.db import normalize_database_url

    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "migrations"))
    config.set_main_option("sqlalchemy.url", normalize_database_url(database_url))
    return config


def check_database_connection(database_url: str) -> tuple[str | None, str | None]:
    engine = create_engine(database_url, pool_pre_ping=True, future=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
            if database_url.startswith("postgresql"):
                db_name, db_user = connection.execute(
                    text("SELECT current_database(), current_user")
                ).one()
                return str(db_name), str(db_user)
            return None, None
    finally:
        engine.dispose()


def explain_operational_error(error: OperationalError) -> None:
    message = str(getattr(error, "orig", error)).lower()
    print("Ошибка подключения к базе данных.")
    if "password authentication failed" in message:
        print("Причина: неверные `POSTGRES_USER`/`POSTGRES_PASSWORD` или `DATABASE_URL`.")
        print("Проверь значения в `.env` и попробуй снова.")
        return
    if "connection refused" in message:
        print("Причина: PostgreSQL не запущен или порт недоступен.")
        print("Запусти сервер и проверь `POSTGRES_HOST`/`POSTGRES_PORT`.")
        return
    if "could not translate host name" in message or "name or service not known" in message:
        print("Причина: некорректный `POSTGRES_HOST`.")
        print("Локально обычно `127.0.0.1`, в Docker Compose — `db`.")
        return
    print(f"Технические детали: {error}")


def main() -> int:
    from app.config import Settings
    from app.db import normalize_database_url

    parser = argparse.ArgumentParser(description="Проверка подключения к БД и запуск миграций Alembic.")
    parser.add_argument(
        "--upgrade-head",
        action="store_true",
        help="После проверки подключения выполнить `alembic upgrade head`.",
    )
    args = parser.parse_args()

    settings = Settings()
    database_url = normalize_database_url(settings.database_url_resolved)
    print(f"DB URL: {mask_database_url(database_url)}")

    try:
        db_name, db_user = check_database_connection(database_url)
    except OperationalError as error:
        explain_operational_error(error)
        return 1
    except SQLAlchemyError as error:
        print(f"Ошибка SQLAlchemy при подключении: {error}")
        return 1

    if db_name and db_user:
        print(f"Подключение успешно: db={db_name}, user={db_user}")
    else:
        print("Подключение успешно.")

    if not args.upgrade_head:
        return 0

    try:
        command.upgrade(build_alembic_config(database_url), "head")
    except Exception as error:  # pragma: no cover - защищаем CLI от падения без трейсбека
        print(f"Не удалось выполнить миграции: {error}")
        return 1

    print("Миграции успешно применены: head.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def normalize_database_url(database_url_or_path: str) -> str:
    raw = (database_url_or_path or "").strip()
    if not raw:
        return "sqlite:///./assistant.db"

    if "://" in raw:
        return raw

    if raw.startswith("sqlite:"):
        return raw

    path = Path(raw).expanduser()
    if path.is_absolute():
        return f"sqlite:///{path}"
    return f"sqlite:///{raw}"


@lru_cache
def get_engine(database_url_or_path: str) -> Engine:
    database_url = normalize_database_url(database_url_or_path)
    connect_args: dict[str, object] = {}
    is_sqlite = database_url.startswith("sqlite")
    if is_sqlite:
        connect_args["check_same_thread"] = False

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
        future=True,
        connect_args=connect_args,
    )
    if is_sqlite:
        event.listen(engine, "connect", _set_sqlite_pragma)
    return engine


def _set_sqlite_pragma(dbapi_connection: object, _connection_record: object) -> None:
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


@lru_cache
def get_session_factory(database_url_or_path: str) -> sessionmaker[Session]:
    engine = get_engine(database_url_or_path)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def session_scope(database_url_or_path: str) -> Generator[Session, None, None]:
    session_factory = get_session_factory(database_url_or_path)
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

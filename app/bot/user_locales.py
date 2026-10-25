from __future__ import annotations

from typing import Literal, cast

from app.db import get_engine, normalize_database_url, session_scope
from app.models import Base, BotUserLocaleModel

BotLocale = Literal["ru", "en"]
SUPPORTED_BOT_LOCALES: tuple[BotLocale, ...] = ("ru", "en")
DEFAULT_BOT_LOCALE: BotLocale = "ru"


def normalize_bot_locale(raw_locale: str) -> BotLocale:
    cleaned = str(raw_locale).strip().lower()
    if cleaned not in SUPPORTED_BOT_LOCALES:
        raise ValueError("Неподдерживаемая локализация")
    return cast(BotLocale, cleaned)


class UserLocalesStore:
    def __init__(self, database_url_or_path: str):
        self.database_url = normalize_database_url(database_url_or_path)
        self.engine = get_engine(self.database_url)
        self._init_db()

    def _init_db(self) -> None:
        if self.database_url.startswith("sqlite"):
            Base.metadata.create_all(self.engine)

    def get_locale(self, user_id: int) -> BotLocale | None:
        with session_scope(self.database_url) as session:
            item = session.get(BotUserLocaleModel, user_id)
            if item is None:
                return None

            raw_locale = str(item.locale).strip().lower()
            if raw_locale not in SUPPORTED_BOT_LOCALES:
                return None
            return cast(BotLocale, raw_locale)

    def set_locale(self, user_id: int, locale: str) -> None:
        normalized_locale = normalize_bot_locale(locale)
        with session_scope(self.database_url) as session:
            existing = session.get(BotUserLocaleModel, user_id)
            if existing is None:
                session.add(BotUserLocaleModel(user_id=user_id, locale=normalized_locale))
                return

            existing.locale = normalized_locale

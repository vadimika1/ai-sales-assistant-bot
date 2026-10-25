from __future__ import annotations

from pathlib import Path

import pytest

from app.bot.user_locales import UserLocalesStore, normalize_bot_locale


def test_user_locales_store_persists_between_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "assistant.db"
    store_1 = UserLocalesStore(str(db_path))

    store_1.set_locale(user_id=7001, locale="ru")
    assert store_1.get_locale(7001) == "ru"

    store_2 = UserLocalesStore(str(db_path))
    assert store_2.get_locale(7001) == "ru"

    store_2.set_locale(user_id=7001, locale="en")
    assert store_2.get_locale(7001) == "en"


def test_normalize_bot_locale_rejects_unknown_value() -> None:
    with pytest.raises(ValueError):
        normalize_bot_locale("de")

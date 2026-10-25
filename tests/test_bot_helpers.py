import pytest

from app.bot.main import (
    INTENT_LABELS,
    build_public_webhook_url,
    extract_suggestion_id,
    localize_value,
    normalize_webhook_path,
    parse_locale_callback_data,
)


def test_extract_suggestion_id_success() -> None:
    assert extract_suggestion_id("ai_accept:42", "ai_accept:") == 42


def test_extract_suggestion_id_invalid_payload() -> None:
    assert extract_suggestion_id("ai_accept:not-a-number", "ai_accept:") is None
    assert extract_suggestion_id("wrong:42", "ai_accept:") is None
    assert extract_suggestion_id(None, "ai_accept:") is None


def test_localize_value_returns_russian_label() -> None:
    assert localize_value("price", INTENT_LABELS) == "Цена"
    assert localize_value("unknown", INTENT_LABELS) == "unknown"


def test_normalize_webhook_path() -> None:
    assert normalize_webhook_path("telegram/webhook") == "/telegram/webhook"
    assert normalize_webhook_path("/telegram/webhook/") == "/telegram/webhook"
    assert normalize_webhook_path("") == "/telegram/webhook"


def test_build_public_webhook_url() -> None:
    assert (
        build_public_webhook_url("https://example.com", "/telegram/webhook")
        == "https://example.com/telegram/webhook"
    )
    assert (
        build_public_webhook_url("https://example.com/custom/path", "/telegram/webhook")
        == "https://example.com/custom/path"
    )


def test_build_public_webhook_url_requires_full_url() -> None:
    with pytest.raises(RuntimeError):
        build_public_webhook_url("example.com", "/telegram/webhook")


def test_parse_locale_callback_data() -> None:
    assert parse_locale_callback_data("lang:ru") == "ru"
    assert parse_locale_callback_data("lang:en") == "en"
    assert parse_locale_callback_data("lang:de") is None
    assert parse_locale_callback_data("ai_accept:1") is None

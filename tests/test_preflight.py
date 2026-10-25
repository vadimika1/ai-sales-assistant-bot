import pytest

from app.config import Settings
from app.preflight import PreflightError, validate_runtime_settings


def test_api_preflight_passes_for_valid_values() -> None:
    settings = Settings.model_construct(
        app_port=8080,
        api_rate_limit_suggest_per_minute=30,
        api_rate_limit_feedback_per_minute=60,
        user_daily_token_limit=0,
        user_token_limit_reserved_response_tokens=280,
        openai_timeout_ms=12000,
    )
    validate_runtime_settings(settings, target="api")


def test_api_preflight_rejects_invalid_rate_limit() -> None:
    settings = Settings.model_construct(
        app_port=8080,
        api_rate_limit_suggest_per_minute=0,
        api_rate_limit_feedback_per_minute=60,
        user_daily_token_limit=0,
        user_token_limit_reserved_response_tokens=280,
        openai_timeout_ms=12000,
    )
    with pytest.raises(PreflightError, match="API_RATE_LIMIT_SUGGEST_PER_MINUTE"):
        validate_runtime_settings(settings, target="api")


def test_api_preflight_rejects_invalid_user_policies_file(tmp_path) -> None:
    policies_path = tmp_path / "user_policies.json"
    policies_path.write_text("{invalid json", encoding="utf-8")
    settings = Settings.model_construct(
        app_port=8080,
        api_rate_limit_suggest_per_minute=30,
        api_rate_limit_feedback_per_minute=60,
        user_daily_token_limit=0,
        user_token_limit_reserved_response_tokens=280,
        openai_timeout_ms=12000,
        user_policies_path=str(policies_path),
    )
    with pytest.raises(PreflightError, match="USER_POLICIES_PATH"):
        validate_runtime_settings(settings, target="api")


def test_bot_preflight_requires_telegram_token() -> None:
    settings = Settings.model_construct(
        telegram_bot_token="",
        api_base_url="http://127.0.0.1:8080",
        bot_api_max_retries=2,
        bot_api_retry_base_ms=300,
        bot_webhook_port=8081,
        bot_run_mode="polling",
        bot_webhook_url="",
    )
    with pytest.raises(PreflightError, match="TELEGRAM_BOT_TOKEN"):
        validate_runtime_settings(settings, target="bot")


def test_bot_preflight_requires_webhook_url_for_webhook_mode() -> None:
    settings = Settings.model_construct(
        telegram_bot_token="123:token",
        api_base_url="http://127.0.0.1:8080",
        bot_api_max_retries=2,
        bot_api_retry_base_ms=300,
        bot_webhook_port=8081,
        bot_run_mode="webhook",
        bot_webhook_url="",
    )
    with pytest.raises(PreflightError, match="BOT_WEBHOOK_URL"):
        validate_runtime_settings(settings, target="bot")

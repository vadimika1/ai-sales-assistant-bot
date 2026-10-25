from __future__ import annotations

import json
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from app.config import Settings
from app.user_policies import parse_user_policies


class PreflightError(RuntimeError):
    """Runtime configuration is invalid for selected process type."""


def _is_http_url(value: str) -> bool:
    raw = value.strip()
    if not raw:
        return False
    parsed = urlsplit(raw)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_port_valid(port: int) -> bool:
    return 1 <= int(port) <= 65535


def validate_runtime_settings(settings: Settings, target: Literal["api", "bot"]) -> None:
    errors: list[str] = []

    if target == "api":
        _collect_api_errors(settings, errors)
    elif target == "bot":
        _collect_bot_errors(settings, errors)
    else:  # pragma: no cover - protected by type hints
        errors.append(f"Неизвестный target preflight: {target}")

    if errors:
        joined = "\n".join(f"- {issue}" for issue in errors)
        raise PreflightError(f"Ошибка preflight-конфигурации ({target}):\n{joined}")


def _collect_api_errors(settings: Settings, errors: list[str]) -> None:
    if not _is_port_valid(settings.app_port):
        errors.append("APP_PORT должен быть в диапазоне 1..65535.")

    if settings.api_rate_limit_suggest_per_minute <= 0:
        errors.append("API_RATE_LIMIT_SUGGEST_PER_MINUTE должен быть > 0.")

    if settings.api_rate_limit_feedback_per_minute <= 0:
        errors.append("API_RATE_LIMIT_FEEDBACK_PER_MINUTE должен быть > 0.")

    if settings.user_daily_token_limit < 0:
        errors.append("USER_DAILY_TOKEN_LIMIT не может быть отрицательным.")

    if settings.user_token_limit_reserved_response_tokens < 1:
        errors.append("USER_TOKEN_LIMIT_RESERVED_RESPONSE_TOKENS должен быть >= 1.")

    if settings.openai_timeout_ms < 1000:
        errors.append("OPENAI_TIMEOUT_MS должен быть >= 1000.")

    policies_path = Path(settings.user_policies_path).expanduser()
    if policies_path.exists():
        try:
            raw = policies_path.read_text(encoding="utf-8")
            payload = json.loads(raw)
            parse_user_policies(payload)
        except Exception:
            errors.append("USER_POLICIES_PATH указывает на невалидный JSON файл политик.")


def _collect_bot_errors(settings: Settings, errors: list[str]) -> None:
    if not settings.telegram_bot_token.strip():
        errors.append("TELEGRAM_BOT_TOKEN не задан.")

    if not _is_http_url(settings.api_base_url):
        errors.append("API_BASE_URL должен быть полным URL, например http://127.0.0.1:8080.")

    if settings.bot_api_max_retries < 0:
        errors.append("BOT_API_MAX_RETRIES не может быть отрицательным.")

    if settings.bot_api_retry_base_ms < 50:
        errors.append("BOT_API_RETRY_BASE_MS должен быть >= 50.")

    if not _is_port_valid(settings.bot_webhook_port):
        errors.append("BOT_WEBHOOK_PORT должен быть в диапазоне 1..65535.")

    if settings.bot_run_mode == "webhook" and not _is_http_url(settings.bot_webhook_url):
        errors.append(
            "Для BOT_RUN_MODE=webhook нужно задать BOT_WEBHOOK_URL (полный URL, например https://example.com/hook)."
        )

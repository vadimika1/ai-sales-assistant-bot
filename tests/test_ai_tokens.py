from __future__ import annotations

from app.ai.tokens import (
    estimate_prompt_tokens,
    estimate_request_total_tokens,
    estimate_text_tokens,
    extract_request_user_id,
)
from app.schemas import AISuggestionRequest


def test_extract_request_user_id_prefers_user_id() -> None:
    payload = AISuggestionRequest(
        manager_message="Тест",
        conversation=[],
        lead_context={"user_id": 123, "telegram_user_id": 999},
    )

    assert extract_request_user_id(payload) == "123"


def test_estimate_tokens_returns_positive_values() -> None:
    payload = AISuggestionRequest(
        manager_message="Клиент спрашивает цену и сроки",
        conversation=[],
        lead_context={"source": "telegram"},
    )
    prompt_tokens = estimate_prompt_tokens(payload, system_prompt="system")
    request_total = estimate_request_total_tokens(
        payload,
        system_prompt="system",
        reserved_completion_tokens=200,
    )

    assert estimate_text_tokens("Привет") > 0
    assert prompt_tokens > 0
    assert request_total >= prompt_tokens + 200

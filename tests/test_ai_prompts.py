from __future__ import annotations

import json

from app.ai.prompts import build_user_prompt
from app.schemas import AISuggestionRequest, ConversationMessage


def test_build_user_prompt_includes_knowledge_context() -> None:
    payload = AISuggestionRequest(
        manager_message="Клиент спрашивает детали",
        conversation=[ConversationMessage(role="client", text="Сколько стоит?")],
        lead_context={"source": "telegram"},
    )

    prompt_json = build_user_prompt(
        payload,
        knowledge_context=[
            {
                "id": "pricing_policy",
                "title": "Правила обсуждения бюджета",
                "text": "Сначала уточняем цель и бюджет.",
                "score": 1.5,
            }
        ],
    )
    parsed = json.loads(prompt_json)

    assert parsed["manager_message"] == "Клиент спрашивает детали"
    assert parsed["knowledge_context"][0]["id"] == "pricing_policy"


def test_build_user_prompt_sets_empty_knowledge_context_by_default() -> None:
    payload = AISuggestionRequest(
        manager_message="Клиент спрашивает детали",
        conversation=[],
        lead_context={},
    )

    parsed = json.loads(build_user_prompt(payload))
    assert parsed["knowledge_context"] == []

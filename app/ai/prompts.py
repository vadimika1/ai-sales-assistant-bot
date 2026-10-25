from __future__ import annotations

import json
from typing import Any

from app.schemas import AISuggestionRequest

SYSTEM_PROMPT = """Ты AI-ассистент менеджера продаж в Telegram.
Твоя задача: предложить аккуратный ответ клиенту и следующий шаг.

Правила:
1) Не выдумывай цены, сроки и гарантии.
2) Если данных не хватает, выбери intent=qualification и попроси уточнение.
3) Дай краткий, вежливый, деловой ответ на русском.
4) Верни только JSON-объект строго по схеме, без markdown и комментариев.
5) Если передан knowledge_context, опирайся только на него как на внутренние факты.

JSON schema:
{
  "suggested_reply": "string",
  "intent": "price|timeline|objection|qualification|general",
  "lead_stage": "new|qualified|proposal|negotiation|won|lost",
  "next_action": "ask_clarifying_question|schedule_call|prepare_proposal|send_follow_up|handoff_to_manager",
  "confidence": 0.0
}
"""


def build_user_prompt(
    payload: AISuggestionRequest,
    knowledge_context: list[dict[str, Any]] | None = None,
) -> str:
    conversation = [item.model_dump() for item in payload.conversation]
    prompt_payload = {
        "manager_message": payload.manager_message,
        "conversation": conversation,
        "lead_context": payload.lead_context or {},
        "knowledge_context": knowledge_context or [],
    }
    return json.dumps(prompt_payload, ensure_ascii=False)

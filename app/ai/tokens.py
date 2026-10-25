from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any

from app.schemas import AISuggestionRequest


@dataclass(frozen=True)
class TokenUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


def extract_request_user_id(payload: AISuggestionRequest) -> str | None:
    context = payload.lead_context
    if not isinstance(context, dict):
        return None

    for key in ("user_id", "telegram_user_id", "manager_user_id"):
        raw = context.get(key)
        if raw is None:
            continue
        user_id = str(raw).strip()
        if user_id:
            return user_id
    return None


def estimate_text_tokens(text: str) -> int:
    normalized = (text or "").strip()
    if not normalized:
        return 0
    # Простая эвристика: ~1 токен на 4 символа для русского/английского текста.
    return max(1, math.ceil(len(normalized) / 4))


def estimate_prompt_tokens(
    payload: AISuggestionRequest,
    system_prompt: str = "",
    knowledge_context: list[dict[str, Any]] | None = None,
) -> int:
    conversation = [item.model_dump() for item in payload.conversation]
    blob = {
        "system_prompt": system_prompt,
        "manager_message": payload.manager_message,
        "conversation": conversation,
        "lead_context": payload.lead_context or {},
        "knowledge_context": knowledge_context or [],
    }
    serialized = json.dumps(blob, ensure_ascii=False)
    return estimate_text_tokens(serialized)


def estimate_request_total_tokens(
    payload: AISuggestionRequest,
    system_prompt: str = "",
    knowledge_context: list[dict[str, Any]] | None = None,
    reserved_completion_tokens: int = 280,
) -> int:
    prompt_tokens = estimate_prompt_tokens(payload, system_prompt, knowledge_context)
    return prompt_tokens + max(1, reserved_completion_tokens)


def normalize_token_usage(
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    estimated_prompt_tokens: int,
    estimated_completion_tokens: int,
) -> TokenUsage:
    safe_prompt = int(prompt_tokens) if int(prompt_tokens) > 0 else max(0, estimated_prompt_tokens)
    safe_completion = (
        int(completion_tokens) if int(completion_tokens) > 0 else max(0, estimated_completion_tokens)
    )
    safe_total = int(total_tokens) if int(total_tokens) > 0 else safe_prompt + safe_completion

    # Если total получен из провайдера, но prompt/completion не вернулись, сохраняем консистентность.
    if safe_total > 0 and (safe_prompt + safe_completion) == 0:
        safe_prompt = max(1, estimated_prompt_tokens)
        safe_completion = max(0, safe_total - safe_prompt)

    return TokenUsage(
        prompt_tokens=max(0, safe_prompt),
        completion_tokens=max(0, safe_completion),
        total_tokens=max(0, safe_total),
    )

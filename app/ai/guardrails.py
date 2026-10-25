from __future__ import annotations

import re

from app.schemas import AISuggestion, AISuggestionRequest

SAFE_FALLBACK_REPLY = (
    "Спасибо за сообщение. Чтобы дать точный ответ без предположений, уточните, пожалуйста, "
    "цель задачи, ориентир по срокам и бюджет. После этого подготовлю корректное предложение."
)

_RISKY_PROMISE_RE = re.compile(
    r"(гарантир|гаранти|100\s*%|\bточно\b|обеща|без\s+риска|абсолютно)",
    re.IGNORECASE,
)
_NUMERIC_CLAIM_RE = re.compile(
    r"(\d+[ \t]*(?:₽|руб|рубл|usd|доллар|eur|€|дн|дней|дня|недел|недели|час|часа|часов))",
    re.IGNORECASE,
)


def apply_suggestion_guardrails(
    suggestion: AISuggestion,
    payload: AISuggestionRequest,
) -> tuple[AISuggestion, list[str]]:
    reasons: list[str] = []
    normalized_reply = _normalize_whitespace(suggestion.suggested_reply)

    if _contains_risky_promise(normalized_reply):
        reasons.append("risky_promise")

    if _contains_unverified_numeric_claim(normalized_reply, payload):
        reasons.append("unverified_numeric_claim")

    if not reasons:
        if normalized_reply != suggestion.suggested_reply:
            suggestion = suggestion.model_copy(update={"suggested_reply": normalized_reply})
        return suggestion, reasons

    guarded_suggestion = suggestion.model_copy(
        update={
            "suggested_reply": SAFE_FALLBACK_REPLY,
            "intent": "qualification",
            "lead_stage": "new",
            "next_action": "ask_clarifying_question",
            "confidence": min(float(suggestion.confidence), 0.35),
        }
    )
    return guarded_suggestion, reasons


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _contains_risky_promise(reply: str) -> bool:
    return _RISKY_PROMISE_RE.search(reply) is not None


def _contains_unverified_numeric_claim(reply: str, payload: AISuggestionRequest) -> bool:
    source_text = payload.manager_message + " " + " ".join(msg.text for msg in payload.conversation)
    if re.search(r"\d", source_text):
        return False
    return _NUMERIC_CLAIM_RE.search(reply) is not None

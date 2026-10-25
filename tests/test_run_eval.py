from __future__ import annotations

from app.schemas import AISuggestion, AISuggestionMeta, AISuggestionResponse
from scripts.run_eval import evaluate_case


def _response(
    *,
    intent: str = "general",
    next_action: str = "ask_clarifying_question",
    lead_stage: str = "new",
    reply: str = "Спасибо. Уточните цель, срок и бюджет.",
) -> AISuggestionResponse:
    return AISuggestionResponse(
        data=AISuggestion(
            suggested_reply=reply,
            intent=intent,  # type: ignore[arg-type]
            lead_stage=lead_stage,  # type: ignore[arg-type]
            next_action=next_action,  # type: ignore[arg-type]
            confidence=0.5,
        ),
        meta=AISuggestionMeta(model="test-model", fallback_used=False, latency_ms=1),
    )


def test_evaluate_case_checks_expected_next_action() -> None:
    case = {
        "id": "case-1",
        "manager_message": "Тест",
        "conversation": [],
        "lead_context": {},
        "expected_next_action": "schedule_call",
    }
    result = evaluate_case(case, _response(next_action="ask_clarifying_question"))
    assert not result.passed
    assert "expected_next_action" in result.message


def test_evaluate_case_checks_required_and_forbidden_substrings() -> None:
    case_required = {
        "id": "case-required",
        "manager_message": "Тест",
        "conversation": [],
        "lead_context": {},
        "required_reply_substrings": ["цель", "бюджет"],
    }
    failed_required = evaluate_case(case_required, _response(reply="Уточните цель."))
    assert not failed_required.passed
    assert "required substring missing" in failed_required.message

    case_forbidden = {
        "id": "case-forbidden",
        "manager_message": "Тест",
        "conversation": [],
        "lead_context": {},
        "forbidden_reply_substrings": ["гарантир"],
    }
    failed_forbidden = evaluate_case(case_forbidden, _response(reply="Мы гарантируем результат."))
    assert not failed_forbidden.passed
    assert "forbidden substring found" in failed_forbidden.message

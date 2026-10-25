from app.ai.guardrails import SAFE_FALLBACK_REPLY, apply_suggestion_guardrails
from app.schemas import AISuggestion, AISuggestionRequest


def test_guardrails_rewrite_risky_promise_reply() -> None:
    payload = AISuggestionRequest(
        manager_message="Клиент просит коммерческое предложение",
        conversation=[],
        lead_context={},
    )
    suggestion = AISuggestion(
        suggested_reply="Гарантируем 100% результат и точный рост продаж.",
        intent="general",
        lead_stage="qualified",
        next_action="prepare_proposal",
        confidence=0.9,
    )

    guarded, reasons = apply_suggestion_guardrails(suggestion, payload)

    assert "risky_promise" in reasons
    assert guarded.suggested_reply == SAFE_FALLBACK_REPLY
    assert guarded.intent == "qualification"
    assert guarded.next_action == "ask_clarifying_question"
    assert guarded.confidence <= 0.35


def test_guardrails_rewrite_unverified_numeric_claim() -> None:
    payload = AISuggestionRequest(
        manager_message="Клиент интересуется деталями",
        conversation=[],
        lead_context={},
    )
    suggestion = AISuggestion(
        suggested_reply="Сделаем за 7 дней и бюджет будет 30 000 ₽.",
        intent="timeline",
        lead_stage="qualified",
        next_action="schedule_call",
        confidence=0.7,
    )

    guarded, reasons = apply_suggestion_guardrails(suggestion, payload)

    assert "unverified_numeric_claim" in reasons
    assert guarded.suggested_reply == SAFE_FALLBACK_REPLY


def test_guardrails_keep_valid_reply_when_numbers_are_in_source() -> None:
    payload = AISuggestionRequest(
        manager_message="Клиент пишет: бюджет 30000 и срок 7 дней",
        conversation=[],
        lead_context={},
    )
    suggestion = AISuggestion(
        suggested_reply="Подтверждаю: ориентир 30000 ₽ и срок 7 дней.",
        intent="price",
        lead_stage="qualified",
        next_action="prepare_proposal",
        confidence=0.66,
    )

    guarded, reasons = apply_suggestion_guardrails(suggestion, payload)

    assert reasons == []
    assert guarded.model_dump() == suggestion.model_dump()


def test_guardrails_do_not_flag_word_tochnoe() -> None:
    payload = AISuggestionRequest(
        manager_message="Клиент попросил детали",
        conversation=[],
        lead_context={},
    )
    suggestion = AISuggestion(
        suggested_reply="Чтобы дать точное предложение, уточните бюджет и сроки.",
        intent="qualification",
        lead_stage="new",
        next_action="ask_clarifying_question",
        confidence=0.5,
    )

    guarded, reasons = apply_suggestion_guardrails(suggestion, payload)

    assert reasons == []
    assert guarded.model_dump() == suggestion.model_dump()

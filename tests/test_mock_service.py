from app.ai.service import MockAssistantService
from app.schemas import AISuggestionRequest


def test_mock_service_detects_price_intent_for_word_cenu() -> None:
    service = MockAssistantService()
    payload = AISuggestionRequest(
        manager_message="Клиент спрашивает цену услуги",
        conversation=[],
        lead_context={},
    )

    result = service.suggest(payload)

    assert result.data.intent == "price"
    assert result.meta.total_tokens > 0
    assert result.meta.prompt_tokens > 0

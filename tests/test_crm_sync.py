import httpx

from app.config import Settings
from app.crm.sync import HttpCRMSyncService
from app.schemas import AISuggestion, AISuggestionRequest


def _build_settings(
    *,
    max_retries: int = 2,
    retry_base_ms: int = 100,
) -> Settings:
    return Settings.model_construct(
        crm_sync_url="https://crm.example.com/sync",
        crm_sync_token="crm-token",
        crm_sync_timeout_ms=3000,
        crm_sync_max_retries=max_retries,
        crm_sync_retry_base_ms=retry_base_ms,
    )


def _build_request() -> AISuggestionRequest:
    return AISuggestionRequest(
        manager_message="Клиент хочет обсудить цену и сроки запуска",
        conversation=[],
        lead_context={"source": "telegram"},
    )


def _build_suggestion() -> AISuggestion:
    return AISuggestion(
        suggested_reply="Спасибо за запрос. Уточню бюджет и сроки.",
        intent="price",
        lead_stage="qualified",
        next_action="schedule_call",
        confidence=0.73,
    )


def test_crm_sync_sends_required_payload(monkeypatch) -> None:
    requests: list[dict] = []

    def fake_post(self, url, json, headers):
        requests.append({"url": url, "json": json, "headers": headers})
        request = httpx.Request("POST", url)
        return httpx.Response(200, request=request, json={"ok": True})

    monkeypatch.setattr(httpx.Client, "post", fake_post)

    service = HttpCRMSyncService(_build_settings())
    result = service.sync_suggestion(
        suggestion_id=7,
        payload=_build_request(),
        suggestion=_build_suggestion(),
    )

    assert result.success is True
    assert result.attempts == 1
    assert requests[0]["url"] == "https://crm.example.com/sync"
    assert requests[0]["headers"]["Authorization"] == "Bearer crm-token"
    body = requests[0]["json"]
    assert body["summary"] == "Клиент хочет обсудить цену и сроки запуска"
    assert body["lead_stage"] == "qualified"
    assert body["next_action"] == "schedule_call"
    assert body["source"] == "telegram"


def test_crm_sync_retries_on_transient_status(monkeypatch) -> None:
    status_codes = [503, 200]
    sleep_delays: list[float] = []

    def fake_post(self, url, json, headers):
        request = httpx.Request("POST", url)
        status = status_codes.pop(0)
        return httpx.Response(status, request=request, json={"detail": "temporary issue"})

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    monkeypatch.setattr("app.crm.sync.time.sleep", lambda delay: sleep_delays.append(delay))

    service = HttpCRMSyncService(_build_settings(max_retries=2, retry_base_ms=120))
    result = service.sync_suggestion(
        suggestion_id=7,
        payload=_build_request(),
        suggestion=_build_suggestion(),
    )

    assert result.success is True
    assert result.attempts == 2
    assert len(sleep_delays) == 1

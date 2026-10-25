from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import (
    get_ai_service,
    get_crm_sync_service,
    get_feedback_store,
    get_feedback_rate_limiter,
    get_suggest_rate_limiter,
    get_user_policies_provider,
)
from app.api.main import app
from app.api.rate_limit import InMemoryRateLimiter
from app.config import get_settings
from app.crm.sync import CRMSyncResult
from app.schemas import AISuggestion, AISuggestionMeta, AISuggestionResponse


class FakeService:
    def suggest(self, _payload):
        return AISuggestionResponse(
            data=AISuggestion(
                suggested_reply="Тестовый ответ",
                intent="general",
                lead_stage="new",
                next_action="ask_clarifying_question",
                confidence=0.51,
            ),
            meta=AISuggestionMeta(model="fake-model", fallback_used=False, latency_ms=3),
        )


class FakeStore:
    def save_suggestion(self, _payload, _response):
        return 10

    def save_feedback(self, _payload):
        return 20

    def save_crm_sync_log(
        self,
        suggestion_id: int,
        sync_status: str,
        attempts: int,
        http_status: int | None,
        error_message: str | None = None,
        payload: dict | None = None,
    ):
        return 1

    def get_user_token_usage(self, user_id: str, days: int = 1) -> int:
        return 0


class FakeNoopCRMSyncService:
    def sync_suggestion(self, suggestion_id: int, payload, suggestion):
        return CRMSyncResult(
            attempted=False,
            success=False,
            attempts=0,
            status_code=None,
            error_message=None,
            payload=None,
        )


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_crm_sync_service.cache_clear()
    get_suggest_rate_limiter.cache_clear()
    get_feedback_rate_limiter.cache_clear()
    get_user_policies_provider.cache_clear()


def test_api_requires_service_token_when_configured(monkeypatch) -> None:
    monkeypatch.setenv("API_SERVICE_TOKEN", "secret-token")
    _clear_caches()
    app.dependency_overrides[get_ai_service] = lambda: FakeService()
    app.dependency_overrides[get_feedback_store] = lambda: FakeStore()
    app.dependency_overrides[get_crm_sync_service] = lambda: FakeNoopCRMSyncService()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/suggest",
                json={
                    "manager_message": "Тест",
                    "conversation": [],
                    "lead_context": {},
                },
            )

        assert response.status_code == 401
        assert response.json()["error"]["message"] == "Недействительный service token."
    finally:
        app.dependency_overrides.clear()
        _clear_caches()


def test_api_accepts_valid_service_token(monkeypatch) -> None:
    monkeypatch.setenv("API_SERVICE_TOKEN", "secret-token")
    _clear_caches()
    app.dependency_overrides[get_ai_service] = lambda: FakeService()
    app.dependency_overrides[get_feedback_store] = lambda: FakeStore()
    app.dependency_overrides[get_crm_sync_service] = lambda: FakeNoopCRMSyncService()

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/suggest",
                headers={"X-Service-Token": "secret-token"},
                json={
                    "manager_message": "Тест",
                    "conversation": [],
                    "lead_context": {},
                },
            )

        assert response.status_code == 200
        assert response.json()["meta"]["suggestion_id"] == 10
    finally:
        app.dependency_overrides.clear()
        _clear_caches()


def test_api_rate_limit_for_suggest(monkeypatch) -> None:
    monkeypatch.setenv("API_SERVICE_TOKEN", "")
    _clear_caches()
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60)
    app.dependency_overrides[get_ai_service] = lambda: FakeService()
    app.dependency_overrides[get_feedback_store] = lambda: FakeStore()
    app.dependency_overrides[get_crm_sync_service] = lambda: FakeNoopCRMSyncService()
    app.dependency_overrides[get_suggest_rate_limiter] = lambda: limiter

    try:
        with TestClient(app) as client:
            first = client.post(
                "/api/v1/ai/suggest",
                json={
                    "manager_message": "Первый запрос",
                    "conversation": [],
                    "lead_context": {},
                },
            )
            second = client.post(
                "/api/v1/ai/suggest",
                json={
                    "manager_message": "Второй запрос",
                    "conversation": [],
                    "lead_context": {},
                },
            )

        assert first.status_code == 200
        assert second.status_code == 429
        assert second.headers.get("Retry-After") is not None
    finally:
        app.dependency_overrides.clear()
        _clear_caches()

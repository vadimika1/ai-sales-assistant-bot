from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.ai.service import AIServiceError
from app.api.deps import (
    get_ai_service,
    get_crm_sync_service,
    get_feedback_store,
    get_user_policies_provider,
    verify_service_token,
)
from app.api.main import app
from app.config import get_settings
from app.crm.sync import CRMSyncResult
from app.schemas import AIFeedbackRequest, AISuggestion, AISuggestionMeta, AISuggestionResponse
from app.storage import SuggestionNotFoundError


class FakeService:
    def suggest(self, _payload):
        return AISuggestionResponse(
            data=AISuggestion(
                suggested_reply="Спасибо за запрос. Предлагаю согласовать короткий созвон на 15 минут.",
                intent="qualification",
                lead_stage="new",
                next_action="schedule_call",
                confidence=0.82
            ),
            meta=AISuggestionMeta(model="fake-model", fallback_used=False, latency_ms=10)
        )


class FakeStore:
    def __init__(self) -> None:
        self.crm_logs: list[dict] = []
        self.user_tokens: dict[str, int] = {}

    def save_suggestion(self, _payload, _response):
        return 123

    def save_feedback(self, payload: AIFeedbackRequest):
        assert payload.suggestion_id == 123
        return 999

    def save_crm_sync_log(
        self,
        suggestion_id: int,
        sync_status: str,
        attempts: int,
        http_status: int | None,
        error_message: str | None = None,
        payload: dict | None = None,
    ) -> int:
        self.crm_logs.append(
            {
                "suggestion_id": suggestion_id,
                "sync_status": sync_status,
                "attempts": attempts,
                "http_status": http_status,
                "error_message": error_message,
                "payload": payload,
            }
        )
        return len(self.crm_logs)

    def get_metrics(self, days: int = 7):
        assert days >= 1
        return {
            "period_days": days,
            "suggestions_total": 12,
            "feedback_total": 10,
            "accepted_count": 5,
            "edited_count": 3,
            "rejected_count": 2,
            "acceptance_rate": 0.5,
            "fallback_rate": 0.25,
            "avg_confidence": 0.61,
            "avg_latency_ms": 220.0,
            "prompt_tokens_total": 1200,
            "completion_tokens_total": 600,
            "total_tokens_total": 1800,
            "avg_total_tokens": 150.0,
        }

    def get_user_token_usage(self, user_id: str, days: int = 1) -> int:
        assert days >= 1
        return int(self.user_tokens.get(str(user_id), 0))


class FailingService:
    def suggest(self, _payload):
        raise AIServiceError("primary model failed")


class MissingSuggestionStore(FakeStore):
    def save_feedback(self, payload: AIFeedbackRequest):
        raise SuggestionNotFoundError(f"Suggestion {payload.suggestion_id} not found")


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


class FakeSuccessCRMSyncService:
    def sync_suggestion(self, suggestion_id: int, payload, suggestion):
        return CRMSyncResult(
            attempted=True,
            success=True,
            attempts=2,
            status_code=200,
            error_message=None,
            payload={
                "suggestion_id": suggestion_id,
                "summary": payload.manager_message,
                "lead_stage": suggestion.lead_stage,
                "next_action": suggestion.next_action,
            },
        )


def _clear_runtime_caches() -> None:
    get_settings.cache_clear()
    get_user_policies_provider.cache_clear()


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ai_suggest() -> None:
    app.dependency_overrides[get_ai_service] = lambda: FakeService()
    app.dependency_overrides[get_feedback_store] = lambda: FakeStore()
    app.dependency_overrides[get_crm_sync_service] = lambda: FakeNoopCRMSyncService()
    app.dependency_overrides[verify_service_token] = lambda: None

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/suggest",
                json={
                    "manager_message": "Клиент спрашивает цену и сроки",
                    "conversation": [
                        {"role": "client", "text": "Сколько стоит и когда можно начать?"}
                    ],
                    "lead_context": {"source": "telegram"}
                }
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["data"]["intent"] == "qualification"
        assert payload["data"]["next_action"] == "schedule_call"
        assert payload["meta"]["model"] == "fake-model"
        assert payload["meta"]["suggestion_id"] == 123
    finally:
        app.dependency_overrides.clear()


def test_ai_feedback() -> None:
    app.dependency_overrides[get_feedback_store] = lambda: FakeStore()
    app.dependency_overrides[verify_service_token] = lambda: None

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/feedback",
                json={
                    "suggestion_id": 123,
                    "manager_action": "accepted"
                }
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["data"]["feedback_id"] == 999
        assert payload["data"]["manager_action"] == "accepted"
    finally:
        app.dependency_overrides.clear()


def test_ai_suggest_returns_503_when_ai_service_fails() -> None:
    app.dependency_overrides[get_ai_service] = lambda: FailingService()
    app.dependency_overrides[get_feedback_store] = lambda: FakeStore()
    app.dependency_overrides[get_crm_sync_service] = lambda: FakeNoopCRMSyncService()
    app.dependency_overrides[verify_service_token] = lambda: None

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/suggest",
                json={
                    "manager_message": "Клиент спрашивает цену",
                    "conversation": [],
                    "lead_context": {"source": "telegram"},
                },
            )

        assert response.status_code == 503
        assert response.json()["error"]["message"] == "AI сервис временно недоступен. Попробуйте повторить запрос."
    finally:
        app.dependency_overrides.clear()


def test_ai_feedback_returns_404_when_suggestion_missing() -> None:
    app.dependency_overrides[get_feedback_store] = lambda: MissingSuggestionStore()
    app.dependency_overrides[verify_service_token] = lambda: None

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/feedback",
                json={
                    "suggestion_id": 99999,
                    "manager_action": "accepted",
                },
            )

        assert response.status_code == 404
        assert response.json()["error"]["message"] == "Подсказка не найдена."
    finally:
        app.dependency_overrides.clear()


def test_ai_metrics() -> None:
    app.dependency_overrides[get_feedback_store] = lambda: FakeStore()
    app.dependency_overrides[verify_service_token] = lambda: None

    try:
        with TestClient(app) as client:
            response = client.get("/api/v1/ai/metrics?days=14")

        assert response.status_code == 200
        payload = response.json()
        assert payload["data"]["period_days"] == 14
        assert payload["data"]["suggestions_total"] == 12
        assert payload["data"]["accepted_count"] == 5
        assert payload["data"]["acceptance_rate"] == 0.5
        assert payload["data"]["total_tokens_total"] == 1800
    finally:
        app.dependency_overrides.clear()


def test_ai_suggest_saves_crm_sync_log_when_attempted() -> None:
    store = FakeStore()
    app.dependency_overrides[get_ai_service] = lambda: FakeService()
    app.dependency_overrides[get_feedback_store] = lambda: store
    app.dependency_overrides[get_crm_sync_service] = lambda: FakeSuccessCRMSyncService()
    app.dependency_overrides[verify_service_token] = lambda: None

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/suggest",
                json={
                    "manager_message": "Клиент спрашивает цену и сроки",
                    "conversation": [],
                    "lead_context": {"source": "telegram"},
                },
            )

        assert response.status_code == 200
        assert len(store.crm_logs) == 1
        crm_log = store.crm_logs[0]
        assert crm_log["suggestion_id"] == 123
        assert crm_log["sync_status"] == "success"
        assert crm_log["attempts"] == 2
        assert crm_log["http_status"] == 200
    finally:
        app.dependency_overrides.clear()


def test_ai_suggest_returns_429_when_daily_user_token_limit_exceeded(monkeypatch) -> None:
    monkeypatch.setenv("USER_DAILY_TOKEN_LIMIT", "100")
    _clear_runtime_caches()
    store = FakeStore()
    store.user_tokens["777"] = 95
    app.dependency_overrides[get_ai_service] = lambda: FakeService()
    app.dependency_overrides[get_feedback_store] = lambda: store
    app.dependency_overrides[get_crm_sync_service] = lambda: FakeNoopCRMSyncService()
    app.dependency_overrides[verify_service_token] = lambda: None

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/suggest",
                json={
                    "manager_message": "Клиент спрашивает цену",
                    "conversation": [],
                    "lead_context": {"user_id": "777", "source": "telegram"},
                },
            )

        assert response.status_code == 429
        assert "Дневной лимит AI-токенов для пользователя исчерпан" in response.json()["error"]["message"]
    finally:
        app.dependency_overrides.clear()
        _clear_runtime_caches()


def test_ai_suggest_returns_403_when_user_is_banned(monkeypatch, tmp_path) -> None:
    policies_path = tmp_path / "user_policies.json"
    policies_path.write_text(
        json.dumps(
            {
                "banned_user_ids": ["888"],
                "daily_token_limit_overrides": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("USER_DAILY_TOKEN_LIMIT", "0")
    monkeypatch.setenv("USER_POLICIES_PATH", str(policies_path))
    _clear_runtime_caches()

    app.dependency_overrides[get_ai_service] = lambda: FakeService()
    app.dependency_overrides[get_feedback_store] = lambda: FakeStore()
    app.dependency_overrides[get_crm_sync_service] = lambda: FakeNoopCRMSyncService()
    app.dependency_overrides[verify_service_token] = lambda: None

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/suggest",
                json={
                    "manager_message": "Клиент спрашивает цену",
                    "conversation": [],
                    "lead_context": {"user_id": "888", "source": "telegram"},
                },
            )

        assert response.status_code == 403
        assert response.json()["error"]["message"] == "Пользователь заблокирован для AI-запросов."
    finally:
        app.dependency_overrides.clear()
        _clear_runtime_caches()


def test_ai_suggest_uses_per_user_limit_override(monkeypatch, tmp_path) -> None:
    policies_path = tmp_path / "user_policies.json"
    policies_path.write_text(
        json.dumps(
            {
                "banned_user_ids": [],
                "daily_token_limit_overrides": {"777": 1000},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("USER_DAILY_TOKEN_LIMIT", "100")
    monkeypatch.setenv("USER_POLICIES_PATH", str(policies_path))
    _clear_runtime_caches()

    store = FakeStore()
    store.user_tokens["777"] = 95
    app.dependency_overrides[get_ai_service] = lambda: FakeService()
    app.dependency_overrides[get_feedback_store] = lambda: store
    app.dependency_overrides[get_crm_sync_service] = lambda: FakeNoopCRMSyncService()
    app.dependency_overrides[verify_service_token] = lambda: None

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/suggest",
                json={
                    "manager_message": "Клиент спрашивает цену",
                    "conversation": [],
                    "lead_context": {"user_id": "777", "source": "telegram"},
                },
            )

        assert response.status_code == 200
        assert response.json()["meta"]["suggestion_id"] == 123
    finally:
        app.dependency_overrides.clear()
        _clear_runtime_caches()

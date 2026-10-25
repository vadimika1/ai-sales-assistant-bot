from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import (
    get_feedback_rate_limiter,
    get_suggest_rate_limiter,
)
from app.api.main import app
from app.config import get_settings


def _clear_caches() -> None:
    get_settings.cache_clear()
    get_suggest_rate_limiter.cache_clear()
    get_feedback_rate_limiter.cache_clear()


def test_validation_error_has_unified_shape_and_request_id(monkeypatch) -> None:
    monkeypatch.setenv("API_SERVICE_TOKEN", "")
    _clear_caches()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/suggest",
                json={
                    "conversation": [],
                    "lead_context": {},
                },
            )

        assert response.status_code == 422
        payload = response.json()
        request_id = response.headers.get("x-request-id")
        assert payload["error"]["code"] == "validation_error"
        assert payload["error"]["message"] == "Ошибка валидации запроса."
        assert payload["error"]["request_id"] == request_id
        assert isinstance(payload["error"]["details"], list)
        assert len(payload["error"]["details"]) >= 1
    finally:
        _clear_caches()


def test_http_error_has_unified_shape_and_keeps_incoming_request_id(monkeypatch) -> None:
    monkeypatch.setenv("API_SERVICE_TOKEN", "secret-token")
    _clear_caches()
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/ai/suggest",
                headers={"X-Request-ID": "req-123"},
                json={
                    "manager_message": "Тест",
                    "conversation": [],
                    "lead_context": {},
                },
            )

        assert response.status_code == 401
        payload = response.json()
        assert payload["error"]["code"] == "unauthorized"
        assert payload["error"]["message"] == "Недействительный service token."
        assert payload["error"]["request_id"] == "req-123"
        assert response.headers.get("x-request-id") == "req-123"
    finally:
        _clear_caches()

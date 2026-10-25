from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_feedback_store
from app.api.main import app


class _ReadyConnection:
    def __enter__(self) -> "_ReadyConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        return False

    def execute(self, _statement) -> None:
        return None


class _ReadyEngine:
    def connect(self) -> _ReadyConnection:
        return _ReadyConnection()


class _FailingEngine:
    def connect(self):
        raise RuntimeError("database down")


class _FakeStore:
    def __init__(self, engine) -> None:
        self.engine = engine


def test_health_ready_returns_ok_when_database_is_reachable() -> None:
    app.dependency_overrides[get_feedback_store] = lambda: _FakeStore(_ReadyEngine())
    try:
        with TestClient(app) as client:
            response = client.get("/health/ready")

        assert response.status_code == 200
        assert response.json() == {
            "status": "ok",
            "checks": {
                "database": {
                    "status": "ok",
                }
            },
        }
    finally:
        app.dependency_overrides.clear()


def test_health_ready_returns_503_when_database_is_unreachable() -> None:
    app.dependency_overrides[get_feedback_store] = lambda: _FakeStore(_FailingEngine())
    try:
        with TestClient(app) as client:
            response = client.get("/health/ready")

        assert response.status_code == 503
        assert response.json() == {
            "status": "fail",
            "checks": {
                "database": {
                    "status": "fail",
                    "detail": "database unavailable",
                }
            },
        }
    finally:
        app.dependency_overrides.clear()

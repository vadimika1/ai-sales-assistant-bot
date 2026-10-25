from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.main import app


def test_request_id_is_generated_when_missing() -> None:
    with TestClient(app) as client:
        response = client.get("/health")

    header_value = response.headers.get("x-request-id")
    assert response.status_code == 200
    assert header_value is not None
    assert len(header_value) >= 16


def test_request_id_is_propagated_when_valid_header_provided() -> None:
    request_id = "leadpilot-test-001"
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": request_id})

    assert response.status_code == 200
    assert response.headers.get("x-request-id") == request_id


def test_request_id_is_regenerated_when_header_invalid() -> None:
    invalid_value = "invalid request id"
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": invalid_value})

    generated = response.headers.get("x-request-id")
    assert response.status_code == 200
    assert generated is not None
    assert generated != invalid_value
    assert " " not in generated

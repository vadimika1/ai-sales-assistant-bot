from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Any

import httpx

from app.config import Settings
from app.schemas import AISuggestion, AISuggestionRequest

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CRMSyncResult:
    attempted: bool
    success: bool
    attempts: int
    status_code: int | None
    error_message: str | None
    payload: dict[str, Any] | None = None


class CRMSyncService:
    def sync_suggestion(
        self,
        suggestion_id: int,
        payload: AISuggestionRequest,
        suggestion: AISuggestion,
    ) -> CRMSyncResult:
        raise NotImplementedError


class NoopCRMSyncService(CRMSyncService):
    def sync_suggestion(
        self,
        suggestion_id: int,
        payload: AISuggestionRequest,
        suggestion: AISuggestion,
    ) -> CRMSyncResult:
        return CRMSyncResult(
            attempted=False,
            success=False,
            attempts=0,
            status_code=None,
            error_message=None,
            payload=None,
        )


class HttpCRMSyncService(CRMSyncService):
    _transient_statuses = {408, 429, 500, 502, 503, 504}

    def __init__(self, settings: Settings):
        self.url = settings.crm_sync_url.strip()
        self.token = settings.crm_sync_token.strip()
        self.timeout_seconds = settings.crm_sync_timeout_seconds
        self.max_retries = max(0, settings.crm_sync_max_retries)
        self.retry_base_ms = max(100, settings.crm_sync_retry_base_ms)

    def sync_suggestion(
        self,
        suggestion_id: int,
        payload: AISuggestionRequest,
        suggestion: AISuggestion,
    ) -> CRMSyncResult:
        if not self.url:
            return NoopCRMSyncService().sync_suggestion(suggestion_id, payload, suggestion)

        body = self._build_payload(
            suggestion_id=suggestion_id,
            request_payload=payload,
            suggestion=suggestion,
        )
        headers = self._build_headers()
        max_attempts = self.max_retries + 1

        with httpx.Client(timeout=self.timeout_seconds) as client:
            for attempt_idx in range(max_attempts):
                attempt = attempt_idx + 1
                try:
                    response = client.post(self.url, json=body, headers=headers)
                except httpx.RequestError as error:
                    if attempt_idx < self.max_retries:
                        delay = self._retry_delay_seconds(attempt_idx)
                        logger.warning(
                            "CRM sync request error, retrying",
                            extra={"attempt": attempt, "delay_sec": delay},
                        )
                        time.sleep(delay)
                        continue

                    return CRMSyncResult(
                        attempted=True,
                        success=False,
                        attempts=attempt,
                        status_code=None,
                        error_message=str(error),
                        payload=body,
                    )

                if response.status_code in self._transient_statuses and attempt_idx < self.max_retries:
                    delay = self._retry_delay_seconds(attempt_idx, response)
                    logger.warning(
                        "CRM sync returned retryable status",
                        extra={"status_code": response.status_code, "attempt": attempt, "delay_sec": delay},
                    )
                    time.sleep(delay)
                    continue

                if response.is_success:
                    return CRMSyncResult(
                        attempted=True,
                        success=True,
                        attempts=attempt,
                        status_code=response.status_code,
                        error_message=None,
                        payload=body,
                    )

                return CRMSyncResult(
                    attempted=True,
                    success=False,
                    attempts=attempt,
                    status_code=response.status_code,
                    error_message=self._extract_error(response),
                    payload=body,
                )

        return CRMSyncResult(
            attempted=True,
            success=False,
            attempts=max_attempts,
            status_code=None,
            error_message="Не удалось выполнить CRM sync.",
            payload=body,
        )

    def _build_headers(self) -> dict[str, str]:
        if not self.token:
            return {}
        return {"Authorization": f"Bearer {self.token}"}

    def _retry_delay_seconds(self, attempt_idx: int, response: httpx.Response | None = None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                return max(0.1, float(retry_after))

        base_seconds = self.retry_base_ms / 1000
        return min(base_seconds * (2 ** attempt_idx), 5.0)

    @staticmethod
    def _extract_error(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            text = response.text.strip()
            return text if text else f"HTTP {response.status_code}"

        if isinstance(payload, dict):
            detail = payload.get("detail")
            if isinstance(detail, str) and detail.strip():
                return detail.strip()

        return f"HTTP {response.status_code}"

    def _build_payload(
        self,
        suggestion_id: int,
        request_payload: AISuggestionRequest,
        suggestion: AISuggestion,
    ) -> dict[str, Any]:
        source = "unknown"
        if request_payload.lead_context and isinstance(request_payload.lead_context, dict):
            raw_source = request_payload.lead_context.get("source")
            if isinstance(raw_source, str) and raw_source.strip():
                source = raw_source.strip()

        return {
            "suggestion_id": suggestion_id,
            "summary": self._build_summary(request_payload.manager_message),
            "intent": suggestion.intent,
            "lead_stage": suggestion.lead_stage,
            "next_action": suggestion.next_action,
            "confidence": suggestion.confidence,
            "source": source,
        }

    @staticmethod
    def _build_summary(manager_message: str, max_length: int = 280) -> str:
        normalized = " ".join(manager_message.strip().split())
        if len(normalized) <= max_length:
            return normalized
        return normalized[: max_length - 1].rstrip() + "…"

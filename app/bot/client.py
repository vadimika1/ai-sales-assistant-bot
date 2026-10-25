from __future__ import annotations

import asyncio
import logging

import httpx

from app.schemas import AIFeedbackResponse, AISuggestionResponse


logger = logging.getLogger(__name__)


class AssistantApiClientError(RuntimeError):
    pass


class AssistantApiClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 12.0,
        service_token: str = "",
        max_retries: int = 2,
        retry_base_ms: int = 300,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.service_token = service_token.strip()
        self.max_retries = max(0, max_retries)
        self.retry_base_ms = max(100, retry_base_ms)

    async def suggest(self, manager_message: str, user_id: int | None = None) -> AISuggestionResponse:
        lead_context: dict[str, str] = {"source": "telegram"}
        if user_id is not None:
            lead_context["user_id"] = str(user_id)

        payload = {
            "manager_message": manager_message,
            "conversation": [],
            "lead_context": lead_context,
        }

        response = await self._post_with_retries(endpoint="/api/v1/ai/suggest", payload=payload)
        return AISuggestionResponse.model_validate(response.json())

    async def feedback(
        self,
        suggestion_id: int,
        manager_action: str,
        edited_reply: str | None = None,
        reason: str | None = None,
    ) -> AIFeedbackResponse:
        payload = {
            "suggestion_id": suggestion_id,
            "manager_action": manager_action,
            "edited_reply": edited_reply,
            "reason": reason,
        }

        response = await self._post_with_retries(endpoint="/api/v1/ai/feedback", payload=payload)
        return AIFeedbackResponse.model_validate(response.json())

    async def _post_with_retries(self, endpoint: str, payload: dict) -> httpx.Response:
        headers = self._build_headers()
        transient_statuses = {429, 500, 502, 503, 504}

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout_seconds) as client:
            for attempt in range(self.max_retries + 1):
                try:
                    response = await client.post(endpoint, json=payload, headers=headers)
                except httpx.RequestError as error:
                    if attempt < self.max_retries:
                        delay = self._retry_delay_seconds(attempt)
                        logger.warning(
                            "API request error, retrying",
                            extra={"endpoint": endpoint, "attempt": attempt + 1, "delay_sec": delay},
                        )
                        await asyncio.sleep(delay)
                        continue

                    logger.warning("API request error without retries left", exc_info=True)
                    raise AssistantApiClientError(
                        "Не удалось связаться с AI API. Проверьте доступность сервиса."
                    ) from error

                if response.status_code in transient_statuses and attempt < self.max_retries:
                    delay = self._retry_delay_seconds(attempt, response)
                    logger.warning(
                        "API returned retryable status",
                        extra={
                            "endpoint": endpoint,
                            "status_code": response.status_code,
                            "attempt": attempt + 1,
                            "delay_sec": delay,
                        },
                    )
                    await asyncio.sleep(delay)
                    continue

                self._raise_on_error(response, endpoint=endpoint)
                return response

        raise AssistantApiClientError("Не удалось выполнить запрос к AI API.")

    def _build_headers(self) -> dict[str, str]:
        if not self.service_token:
            return {}
        return {"X-Service-Token": self.service_token}

    def _retry_delay_seconds(self, attempt: int, response: httpx.Response | None = None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after and retry_after.isdigit():
                return max(0.1, float(retry_after))

        base_seconds = self.retry_base_ms / 1000
        return min(base_seconds * (2 ** attempt), 5.0)

    @staticmethod
    def _raise_on_error(response: httpx.Response, endpoint: str) -> None:
        if response.is_success:
            return

        detail = "Неизвестная ошибка"
        try:
            payload = response.json()
            if isinstance(payload, dict):
                raw_detail = payload.get("detail")
                if isinstance(raw_detail, str) and raw_detail.strip():
                    detail = raw_detail.strip()
        except ValueError:
            pass

        logger.warning(
            "API returned non-success status",
            extra={"endpoint": endpoint, "status_code": response.status_code, "detail": detail},
        )
        raise AssistantApiClientError(f"AI API вернул ошибку {response.status_code}: {detail}")

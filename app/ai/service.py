from __future__ import annotations

import json
import logging
import time
from typing import Any, Protocol

from openai import OpenAI

from app.ai.guardrails import apply_suggestion_guardrails
from app.ai.prompts import SYSTEM_PROMPT, build_user_prompt
from app.ai.tokens import estimate_prompt_tokens, estimate_text_tokens, normalize_token_usage
from app.config import Settings
from app.rag.retriever import RetrievedKnowledge, SimpleRAGRetriever
from app.schemas import AISuggestion, AISuggestionMeta, AISuggestionRequest, AISuggestionResponse


class AIServiceError(RuntimeError):
    pass


logger = logging.getLogger(__name__)


class AssistantService(Protocol):
    def suggest(self, payload: AISuggestionRequest) -> AISuggestionResponse:
        ...


class MockAssistantService:
    """
    Локальный fallback без внешнего LLM API.
    Нужен, чтобы бот можно было запускать и тестировать без OPENAI_API_KEY.
    """

    def __init__(
        self,
        retriever: SimpleRAGRetriever | None = None,
        rag_top_k: int = 3,
        rag_min_score: float = 1.0,
    ):
        self.retriever = retriever
        self.rag_top_k = max(1, min(int(rag_top_k), 10))
        self.rag_min_score = max(0.1, float(rag_min_score))

    def suggest(self, payload: AISuggestionRequest) -> AISuggestionResponse:
        started = time.perf_counter()
        text = payload.manager_message.lower()
        knowledge_snippets = _retrieve_knowledge_context(
            retriever=self.retriever,
            payload=payload,
            top_k=self.rag_top_k,
            min_score=self.rag_min_score,
        )

        intent = "general"
        stage = "new"
        next_action = "ask_clarifying_question"
        confidence = 0.45

        if any(word in text for word in ["цена", "цену", "цены", "стоимость", "сколько"]):
            intent = "price"
            stage = "qualified"
            next_action = "prepare_proposal"
            confidence = 0.62
        elif any(word in text for word in ["когда", "срок", "дедлайн"]):
            intent = "timeline"
            stage = "qualified"
            next_action = "schedule_call"
            confidence = 0.60
        elif any(word in text for word in ["дорого", "не подходит", "сомневаюсь"]):
            intent = "objection"
            stage = "negotiation"
            next_action = "schedule_call"
            confidence = 0.58
        elif any(word in text for word in ["бюджет", "ниша", "цель", "kpi"]):
            intent = "qualification"
            stage = "new"
            next_action = "ask_clarifying_question"
            confidence = 0.64

        if knowledge_snippets:
            top_material = knowledge_snippets[0].title
            reply = (
                f"Спасибо за сообщение. По внутреннему материалу «{top_material}» сначала уточните цель, "
                "сроки и бюджет клиента. После этого предложу корректный формат решения."
            )
            confidence = min(confidence + 0.06, 0.9)
        else:
            reply = (
                "Спасибо за сообщение. Чтобы дать точное предложение, уточните, пожалуйста, "
                "цель задачи, ориентир по срокам и бюджет. После этого предложу оптимальный формат работы."
            )

        latency_ms = int((time.perf_counter() - started) * 1000)
        estimated_prompt_tokens = estimate_prompt_tokens(
            payload=payload,
            system_prompt=SYSTEM_PROMPT,
            knowledge_context=[item.to_prompt_dict() for item in knowledge_snippets],
        )
        estimated_completion_tokens = estimate_text_tokens(reply)
        token_usage = normalize_token_usage(
            prompt_tokens=estimated_prompt_tokens,
            completion_tokens=estimated_completion_tokens,
            total_tokens=estimated_prompt_tokens + estimated_completion_tokens,
            estimated_prompt_tokens=estimated_prompt_tokens,
            estimated_completion_tokens=estimated_completion_tokens,
        )
        suggestion = AISuggestion(
            suggested_reply=reply,
            intent=intent,  # type: ignore[arg-type]
            lead_stage=stage,  # type: ignore[arg-type]
            next_action=next_action,  # type: ignore[arg-type]
            confidence=confidence,
        )
        guarded_suggestion, reasons = apply_suggestion_guardrails(suggestion, payload)
        if reasons:
            logger.warning("Mock guardrails applied", extra={"reasons": reasons})

        return AISuggestionResponse(
            data=guarded_suggestion,
            meta=AISuggestionMeta(
                model="mock-heuristic",
                fallback_used=False,
                latency_ms=latency_ms,
                prompt_tokens=token_usage.prompt_tokens,
                completion_tokens=token_usage.completion_tokens,
                total_tokens=token_usage.total_tokens,
            ),
        )


class OpenAIAssistantService:
    def __init__(
        self,
        settings: Settings,
        retriever: SimpleRAGRetriever | None = None,
    ):
        if not settings.openai_api_key:
            raise AIServiceError("OPENAI_API_KEY не задан")

        self.settings = settings
        self.retriever = retriever
        self.rag_top_k = max(1, min(int(settings.rag_top_k), 10))
        self.rag_min_score = max(0.1, float(settings.rag_min_score))
        self.client = OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds)

    def suggest(self, payload: AISuggestionRequest) -> AISuggestionResponse:
        started = time.perf_counter()
        fallback_used = False
        model_used = self.settings.openai_model
        knowledge_snippets = _retrieve_knowledge_context(
            retriever=self.retriever,
            payload=payload,
            top_k=self.rag_top_k,
            min_score=self.rag_min_score,
        )
        estimated_prompt_tokens = estimate_prompt_tokens(
            payload=payload,
            system_prompt=SYSTEM_PROMPT,
            knowledge_context=[item.to_prompt_dict() for item in knowledge_snippets],
        )
        raw_prompt_tokens = 0
        raw_completion_tokens = 0
        raw_total_tokens = 0

        try:
            suggestion, usage_values = self._suggest_with_model(
                self.settings.openai_model,
                payload,
                knowledge_snippets,
            )
            raw_prompt_tokens, raw_completion_tokens, raw_total_tokens = usage_values
        except Exception as primary_error:
            logger.warning("Primary model failed, trying fallback", exc_info=True)
            fallback_model = self.settings.openai_fallback_model
            if not fallback_model:
                raise AIServiceError(f"Ошибка OpenAI: {primary_error}") from primary_error

            fallback_used = True
            model_used = fallback_model
            try:
                suggestion, usage_values = self._suggest_with_model(
                    fallback_model,
                    payload,
                    knowledge_snippets,
                )
                raw_prompt_tokens, raw_completion_tokens, raw_total_tokens = usage_values
            except Exception as fallback_error:
                logger.error("Fallback model failed", exc_info=True)
                raise AIServiceError(
                    f"Ошибка OpenAI primary={primary_error}; fallback={fallback_error}"
                ) from fallback_error

        latency_ms = int((time.perf_counter() - started) * 1000)
        estimated_completion_tokens = estimate_text_tokens(suggestion.suggested_reply)
        token_usage = normalize_token_usage(
            prompt_tokens=raw_prompt_tokens,
            completion_tokens=raw_completion_tokens,
            total_tokens=raw_total_tokens,
            estimated_prompt_tokens=estimated_prompt_tokens,
            estimated_completion_tokens=estimated_completion_tokens,
        )
        guarded_suggestion, reasons = apply_suggestion_guardrails(suggestion, payload)
        if reasons:
            logger.warning(
                "OpenAI guardrails applied",
                extra={"model": model_used, "reasons": reasons, "fallback_used": fallback_used},
            )

        return AISuggestionResponse(
            data=guarded_suggestion,
            meta=AISuggestionMeta(
                model=model_used,
                fallback_used=fallback_used,
                latency_ms=latency_ms,
                prompt_tokens=token_usage.prompt_tokens,
                completion_tokens=token_usage.completion_tokens,
                total_tokens=token_usage.total_tokens,
            ),
        )

    def _suggest_with_model(
        self,
        model: str,
        payload: AISuggestionRequest,
        knowledge_snippets: list[RetrievedKnowledge],
    ) -> tuple[AISuggestion, tuple[int, int, int]]:
        completion = self.client.chat.completions.create(
            model=model,
            temperature=0.2,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": build_user_prompt(
                        payload,
                        knowledge_context=[item.to_prompt_dict() for item in knowledge_snippets],
                    ),
                },
            ],
        )

        message_content = completion.choices[0].message.content
        raw = self._normalize_content(message_content)
        parsed = self._parse_json_object(raw)
        usage = getattr(completion, "usage", None)
        prompt_tokens = _safe_int(getattr(usage, "prompt_tokens", 0))
        completion_tokens = _safe_int(getattr(usage, "completion_tokens", 0))
        total_tokens = _safe_int(getattr(usage, "total_tokens", 0))
        return AISuggestion.model_validate(parsed), (prompt_tokens, completion_tokens, total_tokens)

    @staticmethod
    def _normalize_content(content: Any) -> str:
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                    continue

                if isinstance(item, dict):
                    text = item.get("text")
                    if isinstance(text, str):
                        parts.append(text)
            return "".join(parts)

        raise AIServiceError("Пустой ответ модели")

    @staticmethod
    def _parse_json_object(raw: str) -> dict[str, Any]:
        try:
            obj = json.loads(raw)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass

        first = raw.find("{")
        last = raw.rfind("}")
        if first == -1 or last == -1 or last <= first:
            raise AIServiceError("Модель вернула невалидный JSON")

        try:
            obj = json.loads(raw[first : last + 1])
        except json.JSONDecodeError as error:
            raise AIServiceError("Не удалось распарсить JSON из ответа модели") from error

        if not isinstance(obj, dict):
            raise AIServiceError("JSON-ответ должен быть объектом")

        return obj


def _retrieve_knowledge_context(
    retriever: SimpleRAGRetriever | None,
    payload: AISuggestionRequest,
    top_k: int,
    min_score: float,
) -> list[RetrievedKnowledge]:
    if retriever is None:
        return []

    try:
        return retriever.retrieve(payload=payload, top_k=top_k, min_score=min_score)
    except Exception:
        logger.exception("RAG retrieve failed")
        return []


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0

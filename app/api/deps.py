import hmac
from functools import lru_cache
from typing import Annotated, Optional

from fastapi import Header, HTTPException

from app.ai.service import AssistantService, MockAssistantService, OpenAIAssistantService
from app.api.rate_limit import InMemoryRateLimiter
from app.config import get_settings
from app.crm.sync import CRMSyncService, HttpCRMSyncService, NoopCRMSyncService
from app.rag.retriever import SimpleRAGRetriever
from app.storage import FeedbackStore
from app.user_policies import JsonUserPoliciesProvider


@lru_cache
def get_ai_service() -> AssistantService:
    settings = get_settings()
    retriever = get_rag_retriever()
    if settings.openai_api_key:
        return OpenAIAssistantService(settings=settings, retriever=retriever)
    return MockAssistantService(
        retriever=retriever,
        rag_top_k=settings.rag_top_k,
        rag_min_score=settings.rag_min_score,
    )


@lru_cache
def get_feedback_store() -> FeedbackStore:
    settings = get_settings()
    return FeedbackStore(settings.database_url_resolved)


@lru_cache
def get_user_policies_provider() -> JsonUserPoliciesProvider:
    settings = get_settings()
    return JsonUserPoliciesProvider(settings.user_policies_path)


@lru_cache
def get_rag_retriever() -> SimpleRAGRetriever:
    settings = get_settings()
    return SimpleRAGRetriever.from_json_file(settings.rag_kb_path)


@lru_cache
def get_crm_sync_service() -> CRMSyncService:
    settings = get_settings()
    if settings.crm_sync_url.strip():
        return HttpCRMSyncService(settings)
    return NoopCRMSyncService()


def verify_service_token(
    x_service_token: Annotated[Optional[str], Header(alias="X-Service-Token")] = None,
) -> None:
    settings = get_settings()
    expected_token = settings.api_service_token.strip()
    if not expected_token:
        return

    if not x_service_token or not hmac.compare_digest(x_service_token, expected_token):
        raise HTTPException(status_code=401, detail="Недействительный service token.")


@lru_cache
def get_suggest_rate_limiter() -> InMemoryRateLimiter:
    settings = get_settings()
    return InMemoryRateLimiter(
        limit=settings.api_rate_limit_suggest_per_minute,
        window_seconds=60,
    )


@lru_cache
def get_feedback_rate_limiter() -> InMemoryRateLimiter:
    settings = get_settings()
    return InMemoryRateLimiter(
        limit=settings.api_rate_limit_feedback_per_minute,
        window_seconds=60,
    )

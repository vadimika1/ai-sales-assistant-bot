import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.exc import SQLAlchemyError

from app.ai.prompts import SYSTEM_PROMPT
from app.ai.service import AIServiceError, AssistantService
from app.ai.tokens import estimate_request_total_tokens, extract_request_user_id
from app.api.deps import (
    get_ai_service,
    get_crm_sync_service,
    get_feedback_rate_limiter,
    get_feedback_store,
    get_suggest_rate_limiter,
    get_user_policies_provider,
    verify_service_token,
)
from app.api.rate_limit import InMemoryRateLimiter
from app.config import get_settings
from app.crm.sync import CRMSyncResult, CRMSyncService
from app.schemas import (
    AIFeedbackData,
    AIFeedbackRequest,
    AIFeedbackResponse,
    AIMetricsData,
    AIMetricsResponse,
    AISuggestionRequest,
    AISuggestionResponse,
)
from app.storage import FeedbackStore, SuggestionNotFoundError
from app.user_policies import JsonUserPoliciesProvider

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
logger = logging.getLogger(__name__)


def _build_rate_limit_key(request: Request, route_name: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{route_name}:{client_host}"


@router.post("/suggest", response_model=AISuggestionResponse)
def suggest(
    request: Request,
    payload: AISuggestionRequest,
    _auth: None = Depends(verify_service_token),
    rate_limiter: InMemoryRateLimiter = Depends(get_suggest_rate_limiter),
    service: AssistantService = Depends(get_ai_service),
    crm_sync_service: CRMSyncService = Depends(get_crm_sync_service),
    store: FeedbackStore = Depends(get_feedback_store),
    user_policies_provider: JsonUserPoliciesProvider = Depends(get_user_policies_provider),
) -> AISuggestionResponse:
    retry_after = rate_limiter.hit(_build_rate_limit_key(request, "suggest"))
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Слишком много запросов к AI. Повторите позже.",
            headers={"Retry-After": str(retry_after)},
        )

    _enforce_user_token_limit(
        payload=payload,
        store=store,
        user_policies_provider=user_policies_provider,
    )

    try:
        result = service.suggest(payload)
        suggestion_id = store.save_suggestion(payload, result)
        result.meta.suggestion_id = suggestion_id

        crm_sync_result = _sync_with_crm(
            crm_sync_service=crm_sync_service,
            suggestion_id=suggestion_id,
            payload=payload,
            result=result,
        )
        _save_crm_sync_log(store=store, suggestion_id=suggestion_id, sync_result=crm_sync_result)

        logger.info(
            "AISuggestion generated",
            extra={
                "suggestion_id": suggestion_id,
                "model": result.meta.model,
                "fallback_used": result.meta.fallback_used,
                "latency_ms": result.meta.latency_ms,
                "total_tokens": result.meta.total_tokens,
            },
        )
        if crm_sync_result.attempted and not crm_sync_result.success:
            logger.warning(
                "CRM sync failed",
                extra={
                    "suggestion_id": suggestion_id,
                    "attempts": crm_sync_result.attempts,
                    "status_code": crm_sync_result.status_code,
                    "error_message": crm_sync_result.error_message,
                },
            )
        return result
    except AIServiceError as error:
        logger.warning("AI service failure", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail="AI сервис временно недоступен. Попробуйте повторить запрос.",
        ) from error
    except SQLAlchemyError as error:
        logger.exception("Storage error while saving suggestion")
        raise HTTPException(status_code=500, detail="Не удалось сохранить AI-подсказку.") from error
    except Exception as error:
        logger.exception("Unexpected error in /suggest")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервиса.") from error


def _sync_with_crm(
    crm_sync_service: CRMSyncService,
    suggestion_id: int,
    payload: AISuggestionRequest,
    result: AISuggestionResponse,
) -> CRMSyncResult:
    try:
        return crm_sync_service.sync_suggestion(
            suggestion_id=suggestion_id,
            payload=payload,
            suggestion=result.data,
        )
    except Exception:
        logger.exception("Unexpected CRM sync error")
        return CRMSyncResult(
            attempted=True,
            success=False,
            attempts=1,
            status_code=None,
            error_message="Unexpected CRM sync error",
            payload=None,
        )


def _save_crm_sync_log(store: FeedbackStore, suggestion_id: int, sync_result: CRMSyncResult) -> None:
    if not sync_result.attempted:
        return

    sync_status = "success" if sync_result.success else "failed"
    try:
        store.save_crm_sync_log(
            suggestion_id=suggestion_id,
            sync_status=sync_status,
            attempts=sync_result.attempts,
            http_status=sync_result.status_code,
            error_message=sync_result.error_message,
            payload=sync_result.payload,
        )
    except SQLAlchemyError:
        logger.exception("Storage error while saving CRM sync log")


def _enforce_user_token_limit(
    payload: AISuggestionRequest,
    store: FeedbackStore,
    user_policies_provider: JsonUserPoliciesProvider,
) -> None:
    settings = get_settings()
    user_id = extract_request_user_id(payload)
    user_policies = user_policies_provider.get()

    if user_id and user_policies.is_banned(user_id):
        raise HTTPException(
            status_code=403,
            detail="Пользователь заблокирован для AI-запросов.",
        )

    daily_limit = max(0, int(settings.user_daily_token_limit))
    effective_daily_limit = daily_limit
    if user_id:
        limit_override = user_policies.get_daily_limit_override(user_id)
        if limit_override is not None:
            effective_daily_limit = max(0, limit_override)

    if effective_daily_limit <= 0:
        return

    if not user_id:
        logger.warning("Token limit configured, but request has no user_id in lead_context")
        return

    projected_tokens = estimate_request_total_tokens(
        payload=payload,
        system_prompt=SYSTEM_PROMPT,
        knowledge_context=[],
        reserved_completion_tokens=settings.user_token_limit_reserved_response_tokens,
    )
    consumed_tokens = store.get_user_token_usage(user_id=user_id, days=1)
    if consumed_tokens + projected_tokens <= effective_daily_limit:
        return

    raise HTTPException(
        status_code=429,
        detail=(
            "Дневной лимит AI-токенов для пользователя исчерпан. "
            f"Использовано: {consumed_tokens}, лимит: {effective_daily_limit}."
        ),
    )


@router.post("/feedback", response_model=AIFeedbackResponse)
def feedback(
    request: Request,
    payload: AIFeedbackRequest,
    _auth: None = Depends(verify_service_token),
    rate_limiter: InMemoryRateLimiter = Depends(get_feedback_rate_limiter),
    store: FeedbackStore = Depends(get_feedback_store),
) -> AIFeedbackResponse:
    retry_after = rate_limiter.hit(_build_rate_limit_key(request, "feedback"))
    if retry_after is not None:
        raise HTTPException(
            status_code=429,
            detail="Слишком много запросов к feedback. Повторите позже.",
            headers={"Retry-After": str(retry_after)},
        )

    try:
        feedback_id = store.save_feedback(payload)
        logger.info(
            "AIFeedback saved",
            extra={
                "feedback_id": feedback_id,
                "suggestion_id": payload.suggestion_id,
                "manager_action": payload.manager_action,
            },
        )
        return AIFeedbackResponse(
            data=AIFeedbackData(
                feedback_id=feedback_id,
                suggestion_id=payload.suggestion_id,
                manager_action=payload.manager_action,
            )
        )
    except SuggestionNotFoundError as error:
        logger.warning("Feedback rejected: %s", error)
        raise HTTPException(status_code=404, detail="Подсказка не найдена.") from error
    except SQLAlchemyError as error:
        logger.exception("Storage error while saving feedback")
        raise HTTPException(status_code=500, detail="Не удалось сохранить feedback.") from error
    except Exception as error:
        logger.exception("Unexpected error in /feedback")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервиса.") from error


@router.get("/metrics", response_model=AIMetricsResponse)
def metrics(
    days: int = Query(default=7, ge=1, le=365),
    _auth: None = Depends(verify_service_token),
    store: FeedbackStore = Depends(get_feedback_store),
) -> AIMetricsResponse:
    try:
        metrics_data = store.get_metrics(days=days)
        return AIMetricsResponse(data=AIMetricsData.model_validate(metrics_data))
    except SQLAlchemyError as error:
        logger.exception("Storage error while loading metrics")
        raise HTTPException(status_code=500, detail="Не удалось загрузить метрики.") from error
    except Exception as error:
        logger.exception("Unexpected error in /metrics")
        raise HTTPException(status_code=500, detail="Внутренняя ошибка сервиса.") from error

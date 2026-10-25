from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, inspect, select, text

from app.ai.tokens import extract_request_user_id
from app.db import get_engine, normalize_database_url, session_scope
from app.models import AIFeedbackModel, AISuggestionModel, Base, CRMSyncLogModel
from app.schemas import AIFeedbackRequest, AISuggestionRequest, AISuggestionResponse


class StorageError(RuntimeError):
    pass


class SuggestionNotFoundError(StorageError):
    pass


class FeedbackStore:
    def __init__(self, database_url_or_path: str):
        self.database_url = normalize_database_url(database_url_or_path)
        self.engine = get_engine(self.database_url)
        self._init_db()

    def _init_db(self) -> None:
        # Локальный sqlite продолжает работать без отдельного шага миграций.
        if self.database_url.startswith("sqlite"):
            Base.metadata.create_all(self.engine)
            self._ensure_sqlite_schema_compat()

    def _ensure_sqlite_schema_compat(self) -> None:
        inspector = inspect(self.engine)
        table_names = set(inspector.get_table_names())
        if "ai_suggestions" not in table_names:
            return

        existing_columns = {column["name"] for column in inspector.get_columns("ai_suggestions")}
        required_columns = {
            "request_user_id": "ALTER TABLE ai_suggestions ADD COLUMN request_user_id VARCHAR(128)",
            "prompt_tokens": "ALTER TABLE ai_suggestions ADD COLUMN prompt_tokens INTEGER NOT NULL DEFAULT 0",
            "completion_tokens": "ALTER TABLE ai_suggestions ADD COLUMN completion_tokens INTEGER NOT NULL DEFAULT 0",
            "total_tokens": "ALTER TABLE ai_suggestions ADD COLUMN total_tokens INTEGER NOT NULL DEFAULT 0",
        }

        with self.engine.begin() as connection:
            for column_name, alter_sql in required_columns.items():
                if column_name in existing_columns:
                    continue
                connection.execute(text(alter_sql))

            index_names = {row["name"] for row in inspector.get_indexes("ai_suggestions")}
            if "idx_ai_suggestions_user_created_at" not in index_names:
                connection.execute(
                    text(
                        "CREATE INDEX idx_ai_suggestions_user_created_at "
                        "ON ai_suggestions (request_user_id, created_at)"
                    )
                )

    def save_suggestion(self, payload: AISuggestionRequest, response: AISuggestionResponse) -> int:
        suggestion = AISuggestionModel(
            manager_message=payload.manager_message,
            suggested_reply=response.data.suggested_reply,
            intent=response.data.intent,
            lead_stage=response.data.lead_stage,
            next_action=response.data.next_action,
            confidence=response.data.confidence,
            model=response.meta.model,
            fallback_used=response.meta.fallback_used,
            latency_ms=response.meta.latency_ms,
            request_user_id=extract_request_user_id(payload),
            prompt_tokens=response.meta.prompt_tokens,
            completion_tokens=response.meta.completion_tokens,
            total_tokens=response.meta.total_tokens,
        )

        with session_scope(self.database_url) as session:
            session.add(suggestion)
            session.flush()
            return int(suggestion.id)

    def save_feedback(self, payload: AIFeedbackRequest) -> int:
        with session_scope(self.database_url) as session:
            existing_suggestion = session.execute(
                select(AISuggestionModel.id).where(AISuggestionModel.id == payload.suggestion_id)
            ).scalar_one_or_none()
            if existing_suggestion is None:
                raise SuggestionNotFoundError(f"Suggestion {payload.suggestion_id} not found")

            feedback = AIFeedbackModel(
                suggestion_id=payload.suggestion_id,
                manager_action=payload.manager_action,
                edited_reply=payload.edited_reply,
                reason=payload.reason,
            )
            session.add(feedback)
            session.flush()
            return int(feedback.id)

    def save_crm_sync_log(
        self,
        suggestion_id: int,
        sync_status: str,
        attempts: int,
        http_status: int | None,
        error_message: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> int:
        payload_json = json.dumps(payload, ensure_ascii=False) if payload is not None else None
        sync_log = CRMSyncLogModel(
            suggestion_id=suggestion_id,
            sync_status=sync_status,
            attempts=max(1, attempts),
            http_status=http_status,
            error_message=error_message,
            payload_json=payload_json,
        )

        with session_scope(self.database_url) as session:
            session.add(sync_log)
            session.flush()
            return int(sync_log.id)

    def get_metrics(self, days: int = 7) -> dict[str, Any]:
        period_days = max(1, min(365, int(days)))
        cutoff = datetime.utcnow() - timedelta(days=period_days)

        with session_scope(self.database_url) as session:
            suggestions_total = int(
                session.execute(
                    select(func.count(AISuggestionModel.id)).where(AISuggestionModel.created_at >= cutoff)
                ).scalar_one()
                or 0
            )
            fallback_total = int(
                session.execute(
                    select(func.count(AISuggestionModel.id))
                    .where(AISuggestionModel.created_at >= cutoff)
                    .where(AISuggestionModel.fallback_used.is_(True))
                ).scalar_one()
                or 0
            )

            avg_confidence, avg_latency_ms = session.execute(
                select(
                    func.avg(AISuggestionModel.confidence),
                    func.avg(AISuggestionModel.latency_ms),
                ).where(AISuggestionModel.created_at >= cutoff)
            ).one()
            prompt_tokens_total, completion_tokens_total, total_tokens_total, avg_total_tokens = session.execute(
                select(
                    func.coalesce(func.sum(AISuggestionModel.prompt_tokens), 0),
                    func.coalesce(func.sum(AISuggestionModel.completion_tokens), 0),
                    func.coalesce(func.sum(AISuggestionModel.total_tokens), 0),
                    func.avg(AISuggestionModel.total_tokens),
                ).where(AISuggestionModel.created_at >= cutoff)
            ).one()

            feedback_rows = session.execute(
                select(AIFeedbackModel.manager_action, func.count(AIFeedbackModel.id))
                .where(AIFeedbackModel.created_at >= cutoff)
                .group_by(AIFeedbackModel.manager_action)
            ).all()

        counts = {"accepted": 0, "edited": 0, "rejected": 0}
        for action, count in feedback_rows:
            if action in counts:
                counts[action] = int(count)

        feedback_total = counts["accepted"] + counts["edited"] + counts["rejected"]
        acceptance_rate = counts["accepted"] / feedback_total if feedback_total else 0.0
        fallback_rate = fallback_total / suggestions_total if suggestions_total else 0.0

        return {
            "period_days": period_days,
            "suggestions_total": suggestions_total,
            "feedback_total": feedback_total,
            "accepted_count": counts["accepted"],
            "edited_count": counts["edited"],
            "rejected_count": counts["rejected"],
            "acceptance_rate": acceptance_rate,
            "fallback_rate": fallback_rate,
            "avg_confidence": float(avg_confidence) if avg_confidence is not None else None,
            "avg_latency_ms": float(avg_latency_ms) if avg_latency_ms is not None else None,
            "prompt_tokens_total": int(prompt_tokens_total or 0),
            "completion_tokens_total": int(completion_tokens_total or 0),
            "total_tokens_total": int(total_tokens_total or 0),
            "avg_total_tokens": float(avg_total_tokens) if avg_total_tokens is not None else None,
        }

    def get_user_token_usage(self, user_id: str, days: int = 1) -> int:
        normalized_user_id = str(user_id).strip()
        if not normalized_user_id:
            return 0

        period_days = max(1, min(365, int(days)))
        cutoff = datetime.utcnow() - timedelta(days=period_days)

        with session_scope(self.database_url) as session:
            total = session.execute(
                select(func.coalesce(func.sum(AISuggestionModel.total_tokens), 0))
                .where(AISuggestionModel.created_at >= cutoff)
                .where(AISuggestionModel.request_user_id == normalized_user_id)
            ).scalar_one()
        return int(total or 0)

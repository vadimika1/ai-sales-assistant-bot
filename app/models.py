from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


int_pk_type = BigInteger().with_variant(Integer, "sqlite")


class AISuggestionModel(Base):
    __tablename__ = "ai_suggestions"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="ck_ai_suggestions_confidence_range"),
        Index("idx_ai_suggestions_created_at", "created_at"),
        Index("idx_ai_suggestions_intent", "intent"),
        Index("idx_ai_suggestions_lead_stage", "lead_stage"),
        Index("idx_ai_suggestions_user_created_at", "request_user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(int_pk_type, primary_key=True, autoincrement=True)
    manager_message: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_reply: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(32), nullable=False)
    lead_stage: Mapped[str] = mapped_column(String(32), nullable=False)
    next_action: Mapped[str] = mapped_column(String(64), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    model: Mapped[str] = mapped_column(String(128), nullable=False)
    fallback_used: Mapped[bool] = mapped_column(nullable=False, default=False)
    latency_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    request_user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    feedback_items: Mapped[list["AIFeedbackModel"]] = relationship(
        back_populates="suggestion",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    crm_sync_logs: Mapped[list["CRMSyncLogModel"]] = relationship(
        back_populates="suggestion",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class AIFeedbackModel(Base):
    __tablename__ = "ai_feedback"
    __table_args__ = (
        CheckConstraint(
            "manager_action IN ('accepted', 'edited', 'rejected')",
            name="ck_ai_feedback_manager_action",
        ),
        Index("idx_ai_feedback_suggestion_id", "suggestion_id"),
        Index("idx_ai_feedback_created_at", "created_at"),
    )

    id: Mapped[int] = mapped_column(int_pk_type, primary_key=True, autoincrement=True)
    suggestion_id: Mapped[int] = mapped_column(
        int_pk_type,
        ForeignKey("ai_suggestions.id", ondelete="CASCADE"),
        nullable=False,
    )
    manager_action: Mapped[str] = mapped_column(String(16), nullable=False)
    edited_reply: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    suggestion: Mapped[AISuggestionModel] = relationship(back_populates="feedback_items")


class CRMSyncLogModel(Base):
    __tablename__ = "crm_sync_log"
    __table_args__ = (
        CheckConstraint(
            "sync_status IN ('success', 'failed')",
            name="ck_crm_sync_log_status",
        ),
        CheckConstraint("attempts >= 1", name="ck_crm_sync_log_attempts_positive"),
        Index("idx_crm_sync_log_suggestion_id", "suggestion_id"),
        Index("idx_crm_sync_log_created_at", "created_at"),
        Index("idx_crm_sync_log_status", "sync_status"),
    )

    id: Mapped[int] = mapped_column(int_pk_type, primary_key=True, autoincrement=True)
    suggestion_id: Mapped[int] = mapped_column(
        int_pk_type,
        ForeignKey("ai_suggestions.id", ondelete="CASCADE"),
        nullable=False,
    )
    sync_status: Mapped[str] = mapped_column(String(16), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    http_status: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    payload_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    suggestion: Mapped[AISuggestionModel] = relationship(back_populates="crm_sync_logs")


class BotPendingEditModel(Base):
    __tablename__ = "bot_pending_edits"
    __table_args__ = (
        Index("idx_bot_pending_edits_updated_at", "updated_at"),
    )

    user_id: Mapped[int] = mapped_column(int_pk_type, primary_key=True)
    suggestion_id: Mapped[int] = mapped_column(
        int_pk_type,
        ForeignKey("ai_suggestions.id", ondelete="CASCADE"),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class BotUserLocaleModel(Base):
    __tablename__ = "bot_user_locales"
    __table_args__ = (
        CheckConstraint("locale IN ('ru', 'en')", name="ck_bot_user_locales_locale"),
        Index("idx_bot_user_locales_updated_at", "updated_at"),
    )

    user_id: Mapped[int] = mapped_column(int_pk_type, primary_key=True)
    locale: Mapped[str] = mapped_column(String(8), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

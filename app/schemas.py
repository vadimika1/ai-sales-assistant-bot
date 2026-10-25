from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


class ConversationMessage(BaseModel):
    role: Literal["client", "manager", "system"]
    text: str = Field(min_length=1, max_length=4000)


class AISuggestionRequest(BaseModel):
    manager_message: str = Field(min_length=1, max_length=4000)
    conversation: list[ConversationMessage] = Field(default_factory=list, max_length=30)
    lead_context: dict[str, Any] | None = None


class AISuggestion(BaseModel):
    suggested_reply: str = Field(min_length=1, max_length=4000)
    intent: Literal["price", "timeline", "objection", "qualification", "general"]
    lead_stage: Literal["new", "qualified", "proposal", "negotiation", "won", "lost"]
    next_action: Literal[
        "ask_clarifying_question",
        "schedule_call",
        "prepare_proposal",
        "send_follow_up",
        "handoff_to_manager"
    ]
    confidence: float = Field(ge=0.0, le=1.0)


class AISuggestionMeta(BaseModel):
    model: str
    fallback_used: bool = False
    latency_ms: int = Field(ge=0)
    suggestion_id: int | None = Field(default=None, ge=1)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class AISuggestionResponse(BaseModel):
    data: AISuggestion
    meta: AISuggestionMeta


class AIFeedbackRequest(BaseModel):
    suggestion_id: int = Field(ge=1)
    manager_action: Literal["accepted", "edited", "rejected"]
    edited_reply: str | None = Field(default=None, min_length=1, max_length=4000)
    reason: str | None = Field(default=None, min_length=1, max_length=4000)

    @model_validator(mode="after")
    def validate_payload(self) -> "AIFeedbackRequest":
        if self.manager_action == "edited" and not self.edited_reply:
            raise ValueError("Для manager_action=edited требуется поле edited_reply")
        return self


class AIFeedbackData(BaseModel):
    feedback_id: int = Field(ge=1)
    suggestion_id: int = Field(ge=1)
    manager_action: Literal["accepted", "edited", "rejected"]


class AIFeedbackResponse(BaseModel):
    data: AIFeedbackData


class AIMetricsData(BaseModel):
    period_days: int = Field(ge=1, le=365)
    suggestions_total: int = Field(ge=0)
    feedback_total: int = Field(ge=0)
    accepted_count: int = Field(ge=0)
    edited_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    acceptance_rate: float = Field(ge=0.0, le=1.0)
    fallback_rate: float = Field(ge=0.0, le=1.0)
    avg_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    avg_latency_ms: float | None = Field(default=None, ge=0.0)
    prompt_tokens_total: int = Field(default=0, ge=0)
    completion_tokens_total: int = Field(default=0, ge=0)
    total_tokens_total: int = Field(default=0, ge=0)
    avg_total_tokens: float | None = Field(default=None, ge=0.0)


class AIMetricsResponse(BaseModel):
    data: AIMetricsData

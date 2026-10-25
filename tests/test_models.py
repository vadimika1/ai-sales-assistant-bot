from __future__ import annotations

from app.models import AISuggestionModel


def test_ai_suggestions_has_composite_user_created_at_index() -> None:
    indexes = {index.name: tuple(column.name for column in index.columns) for index in AISuggestionModel.__table__.indexes}
    assert indexes["idx_ai_suggestions_user_created_at"] == ("request_user_id", "created_at")
    assert "idx_ai_suggestions_request_user_id" not in indexes

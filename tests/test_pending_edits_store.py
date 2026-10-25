from pathlib import Path

from app.bot.pending_edits import PendingEditsStore
from app.db import session_scope
from app.models import AISuggestionModel


def test_pending_edits_store_persists_between_instances(tmp_path: Path) -> None:
    sqlite_path = tmp_path / "assistant.db"
    db_url = str(sqlite_path)
    store_1 = PendingEditsStore(db_url)

    with session_scope(db_url) as session:
        suggestion = AISuggestionModel(
            manager_message="Клиент спрашивает цену",
            suggested_reply="Уточните бюджет и сроки.",
            intent="price",
            lead_stage="new",
            next_action="ask_clarifying_question",
            confidence=0.55,
            model="mock-heuristic",
            fallback_used=False,
            latency_ms=1,
        )
        session.add(suggestion)
        session.flush()
        suggestion_id = int(suggestion.id)

    store_1.set_pending(user_id=1001, suggestion_id=suggestion_id)
    assert store_1.get_pending(1001) == suggestion_id

    store_2 = PendingEditsStore(db_url)
    assert store_2.get_pending(1001) == suggestion_id

    store_2.clear_pending(1001)
    assert store_2.get_pending(1001) is None

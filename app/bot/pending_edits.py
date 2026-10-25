from __future__ import annotations

from sqlalchemy import delete

from app.db import get_engine, normalize_database_url, session_scope
from app.models import Base, BotPendingEditModel


class PendingEditsStore:
    def __init__(self, database_url_or_path: str):
        self.database_url = normalize_database_url(database_url_or_path)
        self.engine = get_engine(self.database_url)
        self._init_db()

    def _init_db(self) -> None:
        if self.database_url.startswith("sqlite"):
            Base.metadata.create_all(self.engine)

    def set_pending(self, user_id: int, suggestion_id: int) -> None:
        with session_scope(self.database_url) as session:
            existing = session.get(BotPendingEditModel, user_id)
            if existing is None:
                session.add(BotPendingEditModel(user_id=user_id, suggestion_id=suggestion_id))
                return

            existing.suggestion_id = suggestion_id

    def get_pending(self, user_id: int) -> int | None:
        with session_scope(self.database_url) as session:
            item = session.get(BotPendingEditModel, user_id)
            if item is None:
                return None
            return int(item.suggestion_id)

    def clear_pending(self, user_id: int) -> None:
        with session_scope(self.database_url) as session:
            session.execute(delete(BotPendingEditModel).where(BotPendingEditModel.user_id == user_id))

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserPolicies:
    banned_user_ids: frozenset[str]
    daily_token_limit_overrides: dict[str, int]

    def is_banned(self, user_id: str) -> bool:
        return user_id.strip() in self.banned_user_ids

    def get_daily_limit_override(self, user_id: str) -> int | None:
        return self.daily_token_limit_overrides.get(user_id.strip())


EMPTY_USER_POLICIES = UserPolicies(
    banned_user_ids=frozenset(),
    daily_token_limit_overrides={},
)


def _normalize_user_id(value: Any) -> str | None:
    if value is None:
        return None
    user_id = str(value).strip()
    if not user_id:
        return None
    return user_id


def parse_user_policies(payload: Any) -> UserPolicies:
    if not isinstance(payload, dict):
        raise ValueError("user policies должны быть JSON объектом")

    banned_raw = payload.get("banned_user_ids", [])
    if not isinstance(banned_raw, list):
        raise ValueError("banned_user_ids должен быть массивом")

    overrides_raw = payload.get("daily_token_limit_overrides", {})
    if not isinstance(overrides_raw, dict):
        raise ValueError("daily_token_limit_overrides должен быть объектом")

    banned: set[str] = set()
    for raw_user_id in banned_raw:
        user_id = _normalize_user_id(raw_user_id)
        if user_id is None:
            continue
        banned.add(user_id)

    overrides: dict[str, int] = {}
    for raw_user_id, raw_limit in overrides_raw.items():
        user_id = _normalize_user_id(raw_user_id)
        if user_id is None:
            continue
        try:
            limit = int(raw_limit)
        except (TypeError, ValueError):
            raise ValueError(f"лимит для user_id={user_id} должен быть целым числом") from None
        if limit < 0:
            raise ValueError(f"лимит для user_id={user_id} не может быть отрицательным")
        overrides[user_id] = limit

    return UserPolicies(
        banned_user_ids=frozenset(sorted(banned)),
        daily_token_limit_overrides=overrides,
    )


def load_user_policies_from_path(path: Path) -> UserPolicies:
    if not path.exists():
        return EMPTY_USER_POLICIES

    raw = path.read_text(encoding="utf-8")
    data = json.loads(raw)
    return parse_user_policies(data)


class JsonUserPoliciesProvider:
    def __init__(self, path: str):
        self.path = Path(path).expanduser()
        self._lock = Lock()
        self._cached_mtime_ns: int = -1
        self._cached_value: UserPolicies = EMPTY_USER_POLICIES

    def get(self) -> UserPolicies:
        try:
            mtime_ns = self.path.stat().st_mtime_ns
        except FileNotFoundError:
            self._cached_mtime_ns = -1
            self._cached_value = EMPTY_USER_POLICIES
            return self._cached_value
        except Exception:
            logger.exception("Cannot read user policies file metadata", extra={"path": str(self.path)})
            return self._cached_value

        if mtime_ns == self._cached_mtime_ns:
            return self._cached_value

        with self._lock:
            if mtime_ns == self._cached_mtime_ns:
                return self._cached_value
            try:
                loaded = load_user_policies_from_path(self.path)
            except Exception:
                logger.exception("Failed to parse user policies file", extra={"path": str(self.path)})
                return self._cached_value
            self._cached_mtime_ns = mtime_ns
            self._cached_value = loaded
            return self._cached_value

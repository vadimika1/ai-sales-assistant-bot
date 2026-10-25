from __future__ import annotations

import json

import pytest

from app.user_policies import JsonUserPoliciesProvider, parse_user_policies


def test_parse_user_policies() -> None:
    payload = {
        "banned_user_ids": ["100", " 200 "],
        "daily_token_limit_overrides": {"100": 500, "300": 0},
    }
    policies = parse_user_policies(payload)

    assert policies.is_banned("100")
    assert policies.is_banned("200")
    assert policies.get_daily_limit_override("100") == 500
    assert policies.get_daily_limit_override("300") == 0
    assert policies.get_daily_limit_override("999") is None


def test_parse_user_policies_rejects_negative_limit() -> None:
    payload = {
        "banned_user_ids": [],
        "daily_token_limit_overrides": {"100": -1},
    }
    with pytest.raises(ValueError):
        parse_user_policies(payload)


def test_provider_reads_updated_file(tmp_path) -> None:
    path = tmp_path / "user_policies.json"
    path.write_text(
        json.dumps(
            {
                "banned_user_ids": ["123"],
                "daily_token_limit_overrides": {"123": 200},
            }
        ),
        encoding="utf-8",
    )
    provider = JsonUserPoliciesProvider(str(path))
    first = provider.get()
    assert first.is_banned("123")
    assert first.get_daily_limit_override("123") == 200

    path.write_text(
        json.dumps(
            {
                "banned_user_ids": [],
                "daily_token_limit_overrides": {"123": 900},
            }
        ),
        encoding="utf-8",
    )
    second = provider.get()
    assert not second.is_banned("123")
    assert second.get_daily_limit_override("123") == 900

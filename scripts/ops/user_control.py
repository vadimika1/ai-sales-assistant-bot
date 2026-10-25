#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def _load_env_file(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", maxsplit=1)
        key = key.strip()
        value = value.strip()
        if not key or key in os.environ:
            continue
        if (value.startswith('"') and value.endswith('"')) or (
            value.startswith("'") and value.endswith("'")
        ):
            value = value[1:-1]
        os.environ[key] = value


def _empty_payload() -> dict[str, Any]:
    return {
        "banned_user_ids": [],
        "daily_token_limit_overrides": {},
    }


def _load_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_payload()
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("JSON должен быть объектом")
    payload = _empty_payload()
    payload.update(data)
    if not isinstance(payload["banned_user_ids"], list):
        raise ValueError("banned_user_ids должен быть массивом")
    if not isinstance(payload["daily_token_limit_overrides"], dict):
        raise ValueError("daily_token_limit_overrides должен быть объектом")
    return payload


def _save_payload(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _normalize_user_id(value: str) -> str:
    user_id = str(value).strip()
    if not user_id:
        raise ValueError("user_id не может быть пустым")
    return user_id


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Управление бан-листом и персональными лимитами пользователей.")
    parser.add_argument(
        "--path",
        default=os.getenv("USER_POLICIES_PATH", "./user_policies.json"),
        help="Путь к JSON файлу политик пользователей.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("list", help="Показать текущие политики.")

    p_ban = subparsers.add_parser("ban", help="Заблокировать пользователя.")
    p_ban.add_argument("user_id")

    p_unban = subparsers.add_parser("unban", help="Снять блокировку пользователя.")
    p_unban.add_argument("user_id")

    p_set_limit = subparsers.add_parser("set-limit", help="Установить персональный дневной лимит токенов.")
    p_set_limit.add_argument("user_id")
    p_set_limit.add_argument("tokens", type=int)

    p_clear_limit = subparsers.add_parser("clear-limit", help="Удалить персональный лимит пользователя.")
    p_clear_limit.add_argument("user_id")

    return parser


def _print_summary(payload: dict[str, Any]) -> None:
    banned = sorted(str(item).strip() for item in payload.get("banned_user_ids", []) if str(item).strip())
    overrides = payload.get("daily_token_limit_overrides", {})

    print("User policies:")
    print(f"- banned_user_ids ({len(banned)}): {', '.join(banned) if banned else 'none'}")
    if not overrides:
        print("- daily_token_limit_overrides: none")
        return
    print("- daily_token_limit_overrides:")
    for user_id, limit in sorted(overrides.items(), key=lambda item: str(item[0])):
        print(f"  - {user_id}: {limit}")


def main() -> int:
    _load_env_file(PROJECT_ROOT / ".env")
    parser = _build_parser()
    args = parser.parse_args()

    try:
        policies_path = Path(args.path).expanduser()
        payload = _load_payload(policies_path)

        if args.command == "list":
            _print_summary(payload)
            return 0

        if args.command == "ban":
            user_id = _normalize_user_id(args.user_id)
            banned = set(str(item).strip() for item in payload.get("banned_user_ids", []))
            banned.add(user_id)
            payload["banned_user_ids"] = sorted(item for item in banned if item)
            _save_payload(policies_path, payload)
            print(f"Пользователь {user_id} заблокирован.")
            _print_summary(payload)
            return 0

        if args.command == "unban":
            user_id = _normalize_user_id(args.user_id)
            banned = set(str(item).strip() for item in payload.get("banned_user_ids", []))
            banned.discard(user_id)
            payload["banned_user_ids"] = sorted(item for item in banned if item)
            _save_payload(policies_path, payload)
            print(f"Пользователь {user_id} разблокирован.")
            _print_summary(payload)
            return 0

        if args.command == "set-limit":
            user_id = _normalize_user_id(args.user_id)
            tokens = int(args.tokens)
            if tokens < 0:
                raise ValueError("tokens не может быть отрицательным")
            overrides = dict(payload.get("daily_token_limit_overrides", {}))
            overrides[user_id] = tokens
            payload["daily_token_limit_overrides"] = overrides
            _save_payload(policies_path, payload)
            print(f"Лимит для {user_id} установлен: {tokens}")
            _print_summary(payload)
            return 0

        if args.command == "clear-limit":
            user_id = _normalize_user_id(args.user_id)
            overrides = dict(payload.get("daily_token_limit_overrides", {}))
            overrides.pop(user_id, None)
            payload["daily_token_limit_overrides"] = overrides
            _save_payload(policies_path, payload)
            print(f"Лимит для {user_id} удален.")
            _print_summary(payload)
            return 0

        raise ValueError(f"Неизвестная команда: {args.command}")
    except Exception as error:
        print(f"Ошибка: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

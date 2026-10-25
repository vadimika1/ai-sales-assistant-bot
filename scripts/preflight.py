#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> int:
    from app.config import Settings
    from app.preflight import PreflightError, validate_runtime_settings

    parser = argparse.ArgumentParser(description="Проверка runtime-конфигурации проекта.")
    parser.add_argument(
        "--target",
        choices=["api", "bot", "all"],
        default="all",
        help="Что проверять: API, bot или оба процесса.",
    )
    args = parser.parse_args()

    settings = Settings()
    targets = ["api", "bot"] if args.target == "all" else [args.target]

    for target in targets:
        try:
            validate_runtime_settings(settings, target=target)  # type: ignore[arg-type]
            print(f"[ok] {target}")
        except PreflightError as error:
            print(f"[fail] {target}")
            print(error)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

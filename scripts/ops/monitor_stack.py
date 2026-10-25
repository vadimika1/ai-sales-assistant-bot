#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Any
from urllib import error as urllib_error
from urllib import parse as urllib_parse
from urllib import request as urllib_request


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


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _run_command(cmd: list[str], cwd: Path | None = None) -> tuple[int, str, str]:
    completed = subprocess.run(
        cmd,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
        check=False,
    )
    return completed.returncode, completed.stdout.strip(), completed.stderr.strip()


def _parse_percent(raw_value: str) -> float | None:
    candidate = raw_value.strip().replace("%", "").replace(",", ".")
    if not candidate:
        return None
    try:
        return float(candidate)
    except ValueError:
        return None


def _check_ready(ready_url: str, timeout_seconds: float) -> list[str]:
    issues: list[str] = []
    try:
        with urllib_request.urlopen(ready_url, timeout=max(1.0, timeout_seconds)) as response:
            if int(response.status) != 200:
                issues.append(f"/health/ready вернул HTTP {response.status} (ожидался 200).")
    except urllib_error.URLError as exc:
        issues.append(f"/health/ready недоступен: {exc}")
    except Exception as exc:  # pragma: no cover - safeguard for runtime script
        issues.append(f"Ошибка проверки /health/ready: {exc}")
    return issues


def _get_required_services(raw_services: str) -> list[str]:
    services = [item.strip() for item in raw_services.split(",") if item.strip()]
    return services or ["api", "bot", "db"]


def _check_running_services(project_root: Path, required_services: list[str]) -> list[str]:
    code, stdout, stderr = _run_command(
        ["docker", "compose", "ps", "--services", "--status", "running"],
        cwd=project_root,
    )
    if code != 0:
        details = stderr or stdout or "unknown error"
        return [f"Не удалось получить список запущенных сервисов: {details}"]

    running = {line.strip() for line in stdout.splitlines() if line.strip()}
    missing = [service for service in required_services if service not in running]
    if not missing:
        return []
    return [f"Не запущены сервисы: {', '.join(missing)}"]


def _container_ids(project_root: Path, required_services: list[str]) -> tuple[dict[str, str], list[str]]:
    service_to_container: dict[str, str] = {}
    issues: list[str] = []
    for service in required_services:
        code, stdout, stderr = _run_command(
            ["docker", "compose", "ps", "-q", service],
            cwd=project_root,
        )
        container_id = stdout.strip()
        if code != 0 or not container_id:
            details = stderr or stdout or "container not found"
            issues.append(f"Не найден container id для сервиса `{service}`: {details}")
            continue
        service_to_container[service] = container_id
    return service_to_container, issues


def _check_container_resources(
    service_to_container: dict[str, str],
    cpu_threshold: float,
    mem_threshold: float,
) -> list[str]:
    if not service_to_container:
        return ["Нет container id для проверки CPU/RAM."]

    container_ids = list(service_to_container.values())
    cmd = [
        "docker",
        "stats",
        "--no-stream",
        "--format",
        "{{.ID}}|{{.Name}}|{{.CPUPerc}}|{{.MemPerc}}",
        *container_ids,
    ]
    code, stdout, stderr = _run_command(cmd)
    if code != 0:
        details = stderr or stdout or "unknown error"
        return [f"Не удалось получить docker stats: {details}"]

    by_id = {value: key for key, value in service_to_container.items()}
    seen_ids: set[str] = set()
    issues: list[str] = []
    for line in stdout.splitlines():
        parts = [part.strip() for part in line.split("|")]
        if len(parts) != 4:
            continue
        container_id, _name, cpu_raw, mem_raw = parts
        service_name = by_id.get(container_id)
        if not service_name:
            continue

        seen_ids.add(container_id)
        cpu_percent = _parse_percent(cpu_raw)
        mem_percent = _parse_percent(mem_raw)

        if cpu_percent is not None and cpu_percent >= cpu_threshold:
            issues.append(
                f"Высокий CPU: service={service_name}, cpu={cpu_percent:.2f}% (порог {cpu_threshold:.2f}%)."
            )
        if mem_percent is not None and mem_percent >= mem_threshold:
            issues.append(
                f"Высокая RAM: service={service_name}, mem={mem_percent:.2f}% (порог {mem_threshold:.2f}%)."
            )

    missing_stats = [service for service, cid in service_to_container.items() if cid not in seen_ids]
    if missing_stats:
        issues.append(f"Нет статистики docker stats для сервисов: {', '.join(missing_stats)}")

    return issues


def _check_api_error_logs(
    project_root: Path,
    lookback_minutes: int,
    error_threshold: int,
) -> list[str]:
    if lookback_minutes <= 0 or error_threshold <= 0:
        return []

    code, stdout, stderr = _run_command(
        ["docker", "compose", "logs", "--no-color", "--since", f"{lookback_minutes}m", "api"],
        cwd=project_root,
    )
    if code != 0:
        details = stderr or stdout or "unknown error"
        return [f"Не удалось проверить логи API: {details}"]

    error_patterns = (
        "unexpected error in /suggest",
        "unexpected error in /feedback",
        "unexpected error in /metrics",
        "storage error while saving suggestion",
        "storage error while saving feedback",
        "storage error while loading metrics",
        "unhandled api exception",
    )
    matched = 0
    for line in stdout.splitlines():
        lowered = line.lower()
        if any(pattern in lowered for pattern in error_patterns):
            matched += 1

    if matched >= error_threshold:
        return [
            "Обнаружены server-error события в логах API: "
            f"{matched} за последние {lookback_minutes} мин."
        ]
    return []


def _load_state(state_path: Path) -> dict[str, Any]:
    if not state_path.exists():
        return {}
    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(state_path: Path, payload: dict[str, Any]) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _alert_signature(issues: list[str]) -> str:
    return "|".join(sorted(issue.strip() for issue in issues if issue.strip()))


def _should_send_alert(
    state: dict[str, Any],
    signature: str,
    now_ts: int,
    cooldown_seconds: int,
) -> bool:
    if signature != str(state.get("last_signature", "")):
        return True
    last_sent_ts = int(state.get("last_sent_ts", 0))
    return now_ts - last_sent_ts >= max(60, cooldown_seconds)


def _send_telegram_alert(bot_token: str, chat_id: str, text: str) -> str | None:
    if not bot_token.strip() or not chat_id.strip():
        return "MONITOR_ALERT_TELEGRAM_BOT_TOKEN / MONITOR_ALERT_TELEGRAM_CHAT_ID не заданы."

    url = f"https://api.telegram.org/bot{bot_token.strip()}/sendMessage"
    payload = urllib_parse.urlencode({"chat_id": chat_id.strip(), "text": text}).encode("utf-8")
    req = urllib_request.Request(url, data=payload, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=10) as response:
            if int(response.status) != 200:
                return f"Telegram API вернул HTTP {response.status}"
    except Exception as exc:  # pragma: no cover - network-specific behavior
        return str(exc)
    return None


def main() -> int:
    project_root = Path(__file__).resolve().parents[2]
    _load_env_file(project_root / ".env")

    ready_url = os.getenv("MONITOR_READY_URL", "http://127.0.0.1:8080/health/ready").strip()
    ready_timeout = _env_float("MONITOR_READY_TIMEOUT_SECONDS", 5.0)
    required_services = _get_required_services(os.getenv("MONITOR_REQUIRED_SERVICES", "api,bot,db"))
    cpu_threshold = _env_float("MONITOR_CPU_PERCENT_THRESHOLD", 90.0)
    mem_threshold = _env_float("MONITOR_MEM_PERCENT_THRESHOLD", 90.0)
    log_lookback_minutes = _env_int("MONITOR_LOG_LOOKBACK_MINUTES", 5)
    error_log_threshold = _env_int("MONITOR_ERROR_LOG_THRESHOLD", 1)
    cooldown_seconds = _env_int("MONITOR_ALERT_COOLDOWN_SECONDS", 900)
    state_path = Path(os.getenv("MONITOR_STATE_PATH", str(project_root / ".monitor_state.json")))
    telegram_bot_token = os.getenv("MONITOR_ALERT_TELEGRAM_BOT_TOKEN", "")
    telegram_chat_id = os.getenv("MONITOR_ALERT_TELEGRAM_CHAT_ID", "")

    issues: list[str] = []
    issues.extend(_check_ready(ready_url=ready_url, timeout_seconds=ready_timeout))
    issues.extend(_check_running_services(project_root=project_root, required_services=required_services))

    service_to_container, container_issues = _container_ids(
        project_root=project_root,
        required_services=required_services,
    )
    issues.extend(container_issues)
    issues.extend(
        _check_container_resources(
            service_to_container=service_to_container,
            cpu_threshold=cpu_threshold,
            mem_threshold=mem_threshold,
        )
    )
    issues.extend(
        _check_api_error_logs(
            project_root=project_root,
            lookback_minutes=log_lookback_minutes,
            error_threshold=error_log_threshold,
        )
    )

    now_ts = int(time.time())
    state = _load_state(state_path)

    if issues:
        signature = _alert_signature(issues)
        if _should_send_alert(state, signature=signature, now_ts=now_ts, cooldown_seconds=cooldown_seconds):
            message_lines = [
                "ALERT: ai-sales-assistant-bot",
                *[f"- {issue}" for issue in issues],
            ]
            alert_error = _send_telegram_alert(
                bot_token=telegram_bot_token,
                chat_id=telegram_chat_id,
                text="\n".join(message_lines),
            )
            if alert_error:
                print(f"[monitor] alert not sent: {alert_error}")
            else:
                print("[monitor] alert sent")
            state["last_signature"] = signature
            state["last_sent_ts"] = now_ts

        state["alert_open"] = True
        _save_state(state_path, state)
        print("[monitor] UNHEALTHY")
        for issue in issues:
            print(f"- {issue}")
        return 1

    was_alert_open = bool(state.get("alert_open"))
    if was_alert_open:
        recovery_error = _send_telegram_alert(
            bot_token=telegram_bot_token,
            chat_id=telegram_chat_id,
            text="RECOVERY: ai-sales-assistant-bot снова в норме.",
        )
        if recovery_error:
            print(f"[monitor] recovery alert not sent: {recovery_error}")
        else:
            print("[monitor] recovery alert sent")

    _save_state(
        state_path,
        {
            "alert_open": False,
            "last_signature": "",
            "last_sent_ts": int(state.get("last_sent_ts", 0)),
        },
    )
    print("[monitor] OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())

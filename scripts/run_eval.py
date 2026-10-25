#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

if TYPE_CHECKING:
    from app.schemas import AISuggestionResponse


@dataclass
class EvalResult:
    case_id: str
    passed: bool
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run regression eval for AI suggestion quality.")
    parser.add_argument(
        "--base-url",
        default=os.getenv("API_BASE_URL", "http://127.0.0.1:8080"),
        help="API base url (default from API_BASE_URL env or http://127.0.0.1:8080)",
    )
    parser.add_argument(
        "--cases",
        default="evals/cases.json",
        help="Path to eval cases JSON file",
    )
    parser.add_argument(
        "--service-token",
        default=os.getenv("API_SERVICE_TOKEN", ""),
        help="Optional X-Service-Token for protected API",
    )
    parser.add_argument("--timeout", type=float, default=15.0, help="Request timeout in seconds")
    return parser.parse_args()


def load_cases(path: str) -> list[dict[str, Any]]:
    content = Path(path).read_text(encoding="utf-8")
    cases = json.loads(content)
    if not isinstance(cases, list):
        raise ValueError("cases file must contain JSON array")
    return cases


def evaluate_case(case: dict[str, Any], response: AISuggestionResponse) -> EvalResult:
    from app.ai.guardrails import apply_suggestion_guardrails
    from app.schemas import AISuggestion, AISuggestionRequest

    case_id = str(case.get("id", "unknown"))

    try:
        payload = AISuggestionRequest.model_validate(
            {
                "manager_message": case["manager_message"],
                "conversation": case.get("conversation", []),
                "lead_context": case.get("lead_context", {}),
            }
        )
    except Exception as error:
        return EvalResult(case_id=case_id, passed=False, message=f"invalid case payload: {error}")

    suggestion = AISuggestion.model_validate(response.data.model_dump())
    expected_intent = case.get("expected_intent")
    if expected_intent and suggestion.intent != expected_intent:
        return EvalResult(
            case_id=case_id,
            passed=False,
            message=f"expected_intent={expected_intent}, got={suggestion.intent}",
        )

    expected_next_action = case.get("expected_next_action")
    if expected_next_action and suggestion.next_action != expected_next_action:
        return EvalResult(
            case_id=case_id,
            passed=False,
            message=f"expected_next_action={expected_next_action}, got={suggestion.next_action}",
        )

    expected_lead_stage = case.get("expected_lead_stage")
    if expected_lead_stage and suggestion.lead_stage != expected_lead_stage:
        return EvalResult(
            case_id=case_id,
            passed=False,
            message=f"expected_lead_stage={expected_lead_stage}, got={suggestion.lead_stage}",
        )

    reply_lower = suggestion.suggested_reply.lower()
    required_substrings = case.get("required_reply_substrings", [])
    if isinstance(required_substrings, list):
        for item in required_substrings:
            needle = str(item).strip().lower()
            if not needle:
                continue
            if needle not in reply_lower:
                return EvalResult(
                    case_id=case_id,
                    passed=False,
                    message=f"required substring missing: {needle}",
                )

    forbidden_substrings = case.get("forbidden_reply_substrings", [])
    if isinstance(forbidden_substrings, list):
        for item in forbidden_substrings:
            needle = str(item).strip().lower()
            if not needle:
                continue
            if needle in reply_lower:
                return EvalResult(
                    case_id=case_id,
                    passed=False,
                    message=f"forbidden substring found: {needle}",
                )

    if case.get("must_pass_guardrails", False):
        _guarded, reasons = apply_suggestion_guardrails(suggestion, payload)
        if reasons:
            return EvalResult(
                case_id=case_id,
                passed=False,
                message=f"guardrails would rewrite output, reasons={','.join(reasons)}",
            )

    return EvalResult(case_id=case_id, passed=True, message="ok")


def run() -> int:
    from app.schemas import AISuggestionResponse

    args = parse_args()
    try:
        cases = load_cases(args.cases)
    except Exception as error:
        print(f"Failed to load cases: {error}", file=sys.stderr)
        return 2

    headers: dict[str, str] = {}
    if args.service_token.strip():
        headers["X-Service-Token"] = args.service_token.strip()

    results: list[EvalResult] = []
    with httpx.Client(base_url=args.base_url.rstrip("/"), timeout=args.timeout) as client:
        for case in cases:
            case_id = str(case.get("id", "unknown"))
            payload = {
                "manager_message": case.get("manager_message", ""),
                "conversation": case.get("conversation", []),
                "lead_context": case.get("lead_context", {}),
            }
            try:
                raw = client.post("/api/v1/ai/suggest", json=payload, headers=headers)
            except Exception as error:
                results.append(EvalResult(case_id=case_id, passed=False, message=f"request failed: {error}"))
                continue

            if raw.status_code != 200:
                results.append(
                    EvalResult(case_id=case_id, passed=False, message=f"http={raw.status_code} body={raw.text}")
                )
                continue

            try:
                response = AISuggestionResponse.model_validate(raw.json())
            except Exception as error:
                results.append(EvalResult(case_id=case_id, passed=False, message=f"invalid response: {error}"))
                continue

            results.append(evaluate_case(case, response))

    passed = [item for item in results if item.passed]
    failed = [item for item in results if not item.passed]

    for item in results:
        status = "PASS" if item.passed else "FAIL"
        print(f"[{status}] {item.case_id}: {item.message}")

    print(f"\nSummary: {len(passed)}/{len(results)} passed, {len(failed)} failed")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(run())

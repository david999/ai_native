"""Assert OCR session JSONL trace (rule injection, file reads, severity in code_comment)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

E2E_ROOT = Path(__file__).resolve().parent
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from lib.ocr_session import analyze_gateway_session, find_session_jsonl, parse_session_jsonl
from lib.scenario_manifest import get_scenario_spec

SESSION_JSONL_WAIT_SEC = 45
SESSION_JSONL_POLL_SEC = 2


def _session_spec(scenario_id: str) -> dict[str, Any]:
    spec = get_scenario_spec(scenario_id)
    session = spec.get("session")
    return dict(session) if isinstance(session, dict) else {}


def _wait_for_session_trace(
    gateway_job_id: str,
    *,
    wait_sec: float = SESSION_JSONL_WAIT_SEC,
    poll_sec: float = SESSION_JSONL_POLL_SEC,
) -> dict[str, Any]:
    """Poll until JSONL exists or timeout (telemetry may lag Gateway success)."""
    deadline = time.monotonic() + wait_sec
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        path = find_session_jsonl(gateway_job_id)
        if path is not None:
            parsed = parse_session_jsonl(path)
            parsed["ok"] = True
            parsed["found"] = True
            parsed["gateway_job_id"] = gateway_job_id
            parsed["errors"] = []
            return parsed
        time.sleep(poll_sec)
    if last is None:
        return analyze_gateway_session(gateway_job_id)
    return last


def assert_ocr_session(gateway_job_id: str, scenario_id: str) -> dict[str, Any]:
    cfg = _session_spec(scenario_id)
    if not cfg:
        return {
            "ok": True,
            "skipped": True,
            "scenario_id": scenario_id,
            "gateway_job_id": gateway_job_id,
            "reason": "no session assertions configured",
        }

    trace = _wait_for_session_trace(gateway_job_id)
    errors: list[str] = []
    warnings: list[str] = []

    if not trace.get("found"):
        errors.extend(trace.get("errors") or ["session JSONL not found"])
        return {
            "ok": False,
            "skipped": False,
            "scenario_id": scenario_id,
            "gateway_job_id": gateway_job_id,
            "errors": errors,
            "warnings": warnings,
        }

    if cfg.get("must_rule_injected") and not trace.get("rule_injected"):
        errors.append("rule.json text not found in session llm_request prompts")

    if cfg.get("must_rule_r1_injected") and not trace.get("rule_r1_injected"):
        errors.append("R1 rule (AGENTS.md) not found in session prompts")

    if cfg.get("must_rule_r2_injected") and not trace.get("rule_r2_injected"):
        errors.append("R2 rule (severity prefix) not found in session prompts")

    if cfg.get("must_rule_injected_or_read_agents"):
        if not trace.get("rule_r1_injected") and not trace.get("read_agents"):
            errors.append("expected R1 in prompt or file_read of AGENTS.md")

    min_sev = cfg.get("must_severity_in_trace")
    sev_warnings_only = bool(cfg.get("severity_warnings_only"))
    if min_sev is not None:
        need = int(min_sev)
        got = int(trace.get("severity_in_trace") or 0)
        if got < need:
            msg = f"severity prefixes in trace: expected >= {need}, got {got}"
            if trace.get("rule_r2_injected"):
                msg = f"R2 injected but code_comment severity prefixes {got} < {need}"
            if sev_warnings_only:
                warnings.append(msg)
            else:
                errors.append(msg)

    if cfg.get("warn_if_no_ai_read") and not trace.get("read_ai_rules"):
        warnings.append("no file_read/code_search of .ai/ rules in session trace")

    ok = len(errors) == 0
    return {
        "ok": ok,
        "skipped": False,
        "scenario_id": scenario_id,
        "gateway_job_id": gateway_job_id,
        "errors": errors,
        "warnings": warnings,
        "viewer_hint": trace.get("viewer_hint"),
        "severity_dashboard_hint": trace.get("severity_dashboard_hint"),
        "session_id": trace.get("session_id"),
        "jsonl_path": trace.get("jsonl_path"),
        "rule_injected": trace.get("rule_injected"),
        "rule_r1_injected": trace.get("rule_r1_injected"),
        "rule_r2_injected": trace.get("rule_r2_injected"),
        "read_agents": trace.get("read_agents"),
        "read_ai_rules": trace.get("read_ai_rules"),
        "severity_in_trace": trace.get("severity_in_trace"),
        "files_read": trace.get("files_read"),
        "tool_names": trace.get("tool_names"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Assert OCR session JSONL trace")
    parser.add_argument("--gateway-job-id", required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--report-json", metavar="PATH")
    args = parser.parse_args()

    result = assert_ocr_session(args.gateway_job_id, args.scenario)
    if args.report_json:
        Path(args.report_json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    for w in result.get("warnings") or []:
        print(f"WARN: {w}")
    if result.get("viewer_hint"):
        print(f"Viewer: {result['viewer_hint']}")

    if result.get("skipped"):
        print("SKIP: no session assertions")
        return 0
    if result.get("ok"):
        print("OK OCR session trace")
        return 0
    for err in result.get("errors") or ["assert failed"]:
        print(f"FAIL: {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

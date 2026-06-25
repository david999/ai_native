"""Parse OCR session JSONL telemetry (~/.opencodereview/sessions)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

RULE_R1_MARKER = "请遵循 AGENTS.md"
RULE_R2_MARKER = "每条评审评论必须以"
SEVERITY_RE = re.compile(r"\[(HIGH|MEDIUM|LOW)\]")
AGENTS_NAME_RE = re.compile(r"AGENTS\.md", re.I)
AI_PATH_RE = re.compile(r"\.ai[/\\]", re.I)

VIEWER_BASE = os.environ.get("OCR_VIEWER_URL", "http://localhost:5483").rstrip("/")
SEVERITY_DASHBOARD_BASE = os.environ.get(
    "SEVERITY_DASHBOARD_URL", "http://localhost:5484"
).rstrip("/")


def sessions_root() -> Path:
    env = os.environ.get("OCR_SESSIONS_DIR", "").strip()
    if env:
        return Path(env)
    return Path.home() / ".opencodereview" / "sessions"


def _repo_dir_matches_job(dir_name: str, gateway_job_id: str) -> bool:
    """Match OCR session repo slug ending with ``-{job_id}`` or exactly ``job_id``."""
    if not gateway_job_id:
        return False
    if dir_name == gateway_job_id:
        return True
    suffix = f"-{gateway_job_id}"
    return len(dir_name) > len(gateway_job_id) and dir_name.endswith(suffix)


def find_session_jsonl(gateway_job_id: str) -> Path | None:
    """Locate newest JSONL for a Gateway worktree job_id."""
    root = sessions_root()
    if not root.is_dir() or not gateway_job_id:
        return None

    candidates: list[Path] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        if _repo_dir_matches_job(entry.name, gateway_job_id):
            candidates.extend(entry.glob("*.jsonl"))

    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _messages_blob(obj: dict[str, Any]) -> str:
    if obj.get("type") != "llm_request":
        return ""
    parts: list[str] = []
    for msg in obj.get("messages") or []:
        if isinstance(msg, dict):
            parts.append(str(msg.get("content") or ""))
    return "\n".join(parts)


def _severity_count_in_text(text: str) -> int:
    return len(SEVERITY_RE.findall(text or ""))


def _extract_reads_from_tool_call(obj: dict[str, Any]) -> tuple[str | None, bool]:
    """Return (path_or_name, is_ai_path) from a tool_call record."""
    if obj.get("type") != "tool_call":
        return None, False

    tool = str(obj.get("tool_name") or "")
    args = _parse_tool_arguments(obj.get("arguments"))
    result = str(obj.get("result") or "")

    if tool == "file_read":
        path = str(args.get("file_path") or "")
        if path:
            return path, bool(AI_PATH_RE.search(path))
        return None, False

    if tool == "file_find":
        # file_find only locates paths; read_agents is set on file_read below.
        return None, False

    if tool == "code_search":
        patterns = str(args.get("file_patterns") or "")
        if AI_PATH_RE.search(patterns) or AI_PATH_RE.search(result):
            return ".ai/", True
        return None, False

    return None, False


def parse_session_jsonl(path: Path) -> dict[str, Any]:
    """Analyze OCR telemetry JSONL for rule / tool / severity signals."""
    session_id = ""
    repo_slug = path.parent.name
    cwd = ""

    rule_r1_injected = False
    rule_r2_injected = False
    read_agents = False
    read_ai_rules = False
    severity_in_trace = 0
    files_read: list[str] = []
    tool_names: list[str] = []

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            evt_type = obj.get("type")
            if evt_type == "session_start":
                session_id = str(obj.get("sessionId") or session_id)
                cwd = str(obj.get("cwd") or cwd)
                continue

            blob = _messages_blob(obj)
            if blob:
                if RULE_R1_MARKER in blob:
                    rule_r1_injected = True
                if RULE_R2_MARKER in blob:
                    rule_r2_injected = True

            if evt_type == "tool_call":
                tool = str(obj.get("tool_name") or "")
                if tool:
                    tool_names.append(tool)

                path_read, is_ai = _extract_reads_from_tool_call(obj)
                if path_read:
                    files_read.append(path_read)
                    if AGENTS_NAME_RE.search(path_read):
                        read_agents = True
                    if is_ai or AI_PATH_RE.search(path_read):
                        read_ai_rules = True

                if tool == "code_comment":
                    # Count only tool_call rows; llm_response duplicates the same payload.
                    severity_in_trace += _severity_count_in_text(str(obj.get("arguments") or ""))

            if evt_type == "llm_response":
                for tc in obj.get("tool_calls") or []:
                    if not isinstance(tc, dict):
                        continue
                    name = str(tc.get("name") or "")
                    if name:
                        tool_names.append(name)

    rule_injected = rule_r1_injected or rule_r2_injected
    viewer_hint = ""
    severity_dashboard_hint = ""
    if session_id and repo_slug:
        viewer_hint = f"{VIEWER_BASE}/r/{repo_slug}/{session_id}"
        severity_dashboard_hint = f"{SEVERITY_DASHBOARD_BASE}/r/{repo_slug}/{session_id}"

    return {
        "jsonl_path": str(path),
        "session_id": session_id,
        "repo_slug": repo_slug,
        "cwd": cwd,
        "rule_injected": rule_injected,
        "rule_r1_injected": rule_r1_injected,
        "rule_r2_injected": rule_r2_injected,
        "read_agents": read_agents,
        "read_ai_rules": read_ai_rules,
        "severity_in_trace": severity_in_trace,
        "files_read": sorted(set(files_read)),
        "tool_names": sorted(set(tool_names)),
        "viewer_hint": viewer_hint,
        "severity_dashboard_hint": severity_dashboard_hint,
    }


def analyze_gateway_session(gateway_job_id: str) -> dict[str, Any]:
    """Find and parse OCR session JSONL for a Gateway job_id."""
    path = find_session_jsonl(gateway_job_id)
    if path is None:
        return {
            "ok": False,
            "found": False,
            "gateway_job_id": gateway_job_id,
            "sessions_root": str(sessions_root()),
            "errors": [f"no OCR session JSONL for job_id={gateway_job_id}"],
        }
    parsed = parse_session_jsonl(path)
    parsed["ok"] = True
    parsed["found"] = True
    parsed["gateway_job_id"] = gateway_job_id
    parsed["errors"] = []
    return parsed

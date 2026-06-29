"""session_telemetry.py 单元测试。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from session_telemetry import (
    SeverityCounts,
    count_severities_in_text,
    discover_repos,
    iter_all_sessions,
    list_repo_sessions,
    load_session,
    scan_session_jsonl,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_count_severities_in_text():
    text = "[HIGH] bug\n[MEDIUM] style\n[LOW] nit\n[HIGH] again"
    counts = count_severities_in_text(text)
    assert counts == {"HIGH": 2, "MEDIUM": 1, "LOW": 1}


def test_scan_session_jsonl_code_comment_only(tmp_path: Path):
    repo = tmp_path / "my-repo-abc123"
    jsonl = repo / "sess001.jsonl"
    _write_jsonl(
        jsonl,
        [
            {
                "type": "session_start",
                "sessionId": "sess001",
                "cwd": "/work/datacalc-web",
                "gitBranch": "feat/test",
                "timestamp": "2026-06-24T10:00:00Z",
            },
            {
                "type": "tool_call",
                "tool_name": "code_comment",
                "arguments": json.dumps(
                    {"path": "src/Foo.java", "end_line": 42, "content": "[HIGH] NPE risk"}
                ),
            },
            {
                "type": "tool_call",
                "tool_name": "code_comment",
                "arguments": '{"content": "[MEDIUM] naming"}',
            },
            {
                "type": "llm_response",
                "tool_calls": [{"name": "code_comment", "arguments": "[HIGH] duplicate"}],
            },
        ],
    )

    result = scan_session_jsonl(jsonl)
    assert result.session_id == "sess001"
    assert result.repo_slug == "my-repo-abc123"
    assert result.cwd == "/work/datacalc-web"
    assert result.severity.high == 1
    assert result.severity.medium == 1
    assert result.severity.low == 0
    assert len(result.high_comments) == 1
    assert result.high_comments[0].file_path == "src/Foo.java"
    assert result.high_comments[0].line == 42


def test_discover_repos_and_list_sessions(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))

    repo_a = tmp_path / "repo,group,proj-111"
    _write_jsonl(
        repo_a / "s1.jsonl",
        [
            {"type": "session_start", "sessionId": "s1", "cwd": "/x/proj-a"},
            {
                "type": "tool_call",
                "tool_name": "code_comment",
                "arguments": "[LOW] note",
            },
        ],
    )
    _write_jsonl(
        repo_a / "s2.jsonl",
        [
            {"type": "session_start", "sessionId": "s2", "cwd": "/x/proj-a"},
            {
                "type": "tool_call",
                "tool_name": "code_comment",
                "arguments": "[HIGH] critical",
            },
        ],
    )

    repos = discover_repos(tmp_path)
    assert len(repos) == 1
    assert repos[0].encoded_path == "repo,group,proj-111"
    assert repos[0].session_count == 2
    assert repos[0].severity.high == 1
    assert repos[0].severity.low == 1
    assert repos[0].has_high

    sessions = list_repo_sessions(tmp_path, "repo,group,proj-111")
    assert len(sessions) == 2
    high_session = next(s for s in sessions if s.session_id == "s2")
    assert high_session.has_high


def test_load_session_missing_returns_none(tmp_path: Path):
    assert load_session(tmp_path, "missing", "nope") is None


def test_severity_counts_helpers():
    sc = SeverityCounts(high=2, medium=1, low=3)
    assert sc.total() == 6
    other = SeverityCounts.from_dict({"HIGH": 1, "MEDIUM": 0, "LOW": 2})
    sc.add(other)
    assert sc.high == 3
    assert sc.low == 5


def test_load_session_rejects_path_traversal(tmp_path: Path):
    root = tmp_path / "sessions"
    root.mkdir()
    safe = root / "proj"
    safe.mkdir()
    (safe / "ok.jsonl").write_text(
        '{"type":"session_start","sessionId":"ok"}\n',
        encoding="utf-8",
    )
    assert load_session(root, "../sessions", "ok") is None
    assert load_session(root, "proj", "../ok") is None
    assert load_session(root, "proj", "ok") is not None


def test_discover_repos_display_name_from_newest_session(tmp_path: Path):
    repo = tmp_path / "slug-a"
    _write_jsonl(
        repo / "old.jsonl",
        [
            {"type": "session_start", "sessionId": "old", "cwd": "/work/old-name"},
            {"type": "tool_call", "tool_name": "code_comment", "arguments": "[LOW] x"},
        ],
    )
    _write_jsonl(
        repo / "new.jsonl",
        [
            {"type": "session_start", "sessionId": "new", "cwd": "/work/newest-proj"},
            {"type": "tool_call", "tool_name": "code_comment", "arguments": "[HIGH] x"},
        ],
    )
    import os
    import time

    old_path = repo / "old.jsonl"
    new_path = repo / "new.jsonl"
    os.utime(old_path, (time.time() - 3600, time.time() - 3600))
    os.utime(new_path, (time.time(), time.time()))

    repos = discover_repos(tmp_path)
    assert len(repos) == 1
    assert repos[0].display_name == "newest-proj"


def test_discover_repos_latest_tokens_not_cumulative(tmp_path: Path):
    import os
    import time

    repo = tmp_path / "slug-a"
    _write_jsonl(
        repo / "old.jsonl",
        [
            {"type": "session_start", "sessionId": "old", "cwd": "/work/proj"},
            {
                "type": "llm_response",
                "usage": {"prompt_tokens": 100_000, "completion_tokens": 1_000},
            },
        ],
    )
    _write_jsonl(
        repo / "new.jsonl",
        [
            {"type": "session_start", "sessionId": "new", "cwd": "/work/proj"},
            {
                "type": "llm_response",
                "usage": {"prompt_tokens": 10_000, "completion_tokens": 500},
            },
        ],
    )
    os.utime(repo / "old.jsonl", (time.time() - 3600, time.time() - 3600))
    os.utime(repo / "new.jsonl", (time.time(), time.time()))

    repos = discover_repos(tmp_path)
    assert len(repos) == 1
    assert repos[0].latest_tokens.total == 10_500
    assert repos[0].tokens.total == 111_500


def test_iter_all_sessions_skips_unsafe_repo_dir(tmp_path: Path):
    safe = tmp_path / "proj-safe"
    _write_jsonl(
        safe / "s1.jsonl",
        [
            {"type": "session_start", "sessionId": "s1"},
            {"type": "llm_response", "usage": {"prompt_tokens": 100, "completion_tokens": 10}},
        ],
    )
    unsafe = tmp_path / "bad..repo"
    unsafe.mkdir()
    (unsafe / "skip.jsonl").write_text(
        '{"type":"session_start","sessionId":"skip"}\n',
        encoding="utf-8",
    )

    sessions = iter_all_sessions(tmp_path)
    assert len(sessions) == 1
    assert sessions[0].session_id == "s1"

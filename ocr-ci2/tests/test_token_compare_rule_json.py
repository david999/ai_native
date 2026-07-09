"""token_compare_rule_json.py 单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from session_telemetry import scan_session_jsonl
from token_compare_rule_json import (
    ReviewArm,
    _known_jsonl_paths,
    _restore_rule_json,
    _rule_json_backup,
    _wait_new_session,
    render_markdown,
)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_rule_json_backup_and_restore(tmp_path: Path):
    repo = tmp_path / "proj"
    rule = repo / ".opencodereview" / "rule.json"
    rule.parent.mkdir(parents=True)
    rule.write_text('{"rules":[]}', encoding="utf-8")

    path, backup = _rule_json_backup(repo)
    assert backup is not None
    rule.unlink()
    assert not rule.is_file()

    _restore_rule_json(path, backup)
    assert rule.read_text(encoding="utf-8") == '{"rules":[]}'


def test_wait_new_session_by_cwd(tmp_path: Path, monkeypatch):
    repo = tmp_path / "datacalc-web"
    repo.mkdir()
    sessions = tmp_path / "sessions"
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions))

    slug = sessions / "encoded-repo"
    old = slug / "old.jsonl"
    _write_jsonl(
        old,
        [{"type": "session_start", "sessionId": "old", "cwd": str(repo)}],
    )

    import os
    import time

    time.sleep(0.05)
    before = _known_jsonl_paths(sessions)
    new = slug / "new.jsonl"
    _write_jsonl(
        new,
        [
            {"type": "session_start", "sessionId": "new", "cwd": str(repo)},
            {
                "type": "llm_response",
                "usage": {"prompt_tokens": 1000, "completion_tokens": 50},
            },
        ],
    )
    os.utime(new, (time.time(), time.time()))

    found = _wait_new_session(repo, before=before, started_at=time.time() - 1)
    assert found is not None
    assert found.session_id == "new"
    assert found.tokens.total == 1050


def test_render_markdown_delta():
    from session_telemetry import SessionTelemetry, TokenUsage

    with_arm = ReviewArm(
        label="有 rule.json",
        had_rule_json=True,
        session=SessionTelemetry(
            session_id="aaaa1111-bbbb",
            repo_slug="r",
            tokens=TokenUsage(prompt_tokens=30000, completion_tokens=2000, request_count=10),
            tool_counts={"file_read": 2, "file_find": 1},
        ),
    )
    without_arm = ReviewArm(
        label="无 rule.json",
        had_rule_json=False,
        session=SessionTelemetry(
            session_id="cccc2222-dddd",
            repo_slug="r",
            tokens=TokenUsage(prompt_tokens=20000, completion_tokens=1500, request_count=8),
            tool_counts={"file_read": 1, "file_find": 0},
        ),
    )
    md = render_markdown(with_arm, without_arm, repo=Path("/x/datacalc-web"), from_ref="a", to_ref="b")
    assert "有 rule.json" in md
    assert "无 rule.json" in md
    assert "-10,500" in md


@pytest.mark.skipif(
    not __import__("os").environ.get("OCR_TEST_LIVE"),
    reason="set OCR_TEST_LIVE=1 to run live rule.json token comparison",
)
def test_live_rule_json_token_comparison():
    """Live: two ocr review runs on datacalc-web D05 branch."""
    from token_compare_rule_json import run_comparison

    repo = Path(__file__).resolve().parents[1] / "e2e" / "fixtures" / "datacalc-web"
    with_arm, without_arm = run_comparison(
        repo,
        from_ref="origin/master",
        to_ref="HEAD",
        branch="ocr-test/D05_rule_severity_prefix",
        max_tools=16,
    )
    assert not with_arm.error, with_arm.error
    assert not without_arm.error, without_arm.error
    assert with_arm.session and without_arm.session
    assert with_arm.session.tokens.total > 0
    assert without_arm.session.tokens.total > 0

"""seed_dashboard_demo.py 脚本测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from review_index import load_all_records  # noqa: E402
from seed_dashboard_demo import seed_demo_records  # noqa: E402


def _write_session(sessions_dir: Path, encoded_repo: str, session_id: str, cwd: str) -> None:
    repo_dir = sessions_dir / encoded_repo
    repo_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        {"type": "session_start", "sessionId": session_id, "cwd": cwd, "gitBranch": "feat/demo"},
        {
            "type": "tool_call",
            "tool_name": "code_comment",
            "arguments": json.dumps({"path": "src/Demo.java", "end_line": 10, "content": "[HIGH] demo"}),
        },
    ]
    (repo_dir / f"{session_id}.jsonl").write_text(
        "\n".join(json.dumps(x, ensure_ascii=False) for x in lines) + "\n",
        encoding="utf-8",
    )


def test_seed_demo_records_writes_index(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    index = tmp_path / "review-index.jsonl"
    _write_session(sessions, "demo-repo-a", "s1", "/work/java_group/datacalc-web")
    _write_session(sessions, "demo-repo-b", "s2", "/work/go_group/parser")

    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions))
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(index))

    created = seed_demo_records(index_path=index, sessions_root_path=sessions, per_repo=2)
    assert len(created) == 4
    records = load_all_records(index)
    assert len(records) == 4
    paths = {r.project_path for r in records}
    assert "datacalc-web" in paths
    assert "parser" in paths
    assert any(r.status == "failed" for r in records)


def test_seed_demo_records_dry_run(tmp_path):
    sessions = tmp_path / "sessions"
    index = tmp_path / "review-index.jsonl"
    _write_session(sessions, "only-one", "s1", "/x/demo")
    created = seed_demo_records(
        index_path=index,
        sessions_root_path=sessions,
        per_repo=1,
        dry_run=True,
    )
    assert len(created) == 1
    assert not index.exists()

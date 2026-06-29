"""session_job_link.py 单元测试。"""

from __future__ import annotations

import json

from session_job_link import find_session_jsonl_path, repo_dir_matches_job


def test_repo_dir_matches_job():
    assert repo_dir_matches_job("abc123", "abc123")
    assert repo_dir_matches_job("group,proj,111-abc123", "abc123")
    assert not repo_dir_matches_job("other", "abc123")


def test_find_session_jsonl_path(tmp_path):
    job_id = "job99"
    repo = tmp_path / f"group,proj,111-{job_id}"
    repo.mkdir(parents=True)
    jsonl = repo / "sess.jsonl"
    jsonl.write_text(
        json.dumps({"type": "session_start", "sessionId": "sess", "cwd": "/x"}) + "\n",
        encoding="utf-8",
    )
    found = find_session_jsonl_path(job_id, root=tmp_path)
    assert found == jsonl

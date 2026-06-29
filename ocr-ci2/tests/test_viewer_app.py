"""Severity Dashboard HTTP 路由测试（挂载于 Gateway :8010）。"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OCR_VIEWER_URL", "http://localhost:5483")
    return TestClient(app)


def test_index_empty_sessions(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
    idx = tmp_path / "idx.jsonl"
    idx.write_text("", encoding="utf-8")
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setattr("gateway.review_service.list_active_jobs", lambda: [])
    resp = client.get("/")
    assert resp.status_code == 200
    assert "OCR Gateway Dashboard" in resp.text
    assert "http://localhost:5483" in resp.text


def test_index_with_mr_record(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
    index_path = tmp_path / "idx.jsonl"
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(index_path))
    record = {
        "job_id": "job1",
        "project_id": "111",
        "project_path": "group/demo",
        "mr_iid": "9",
        "target_branch": "main",
        "commit_sha": "abc12345",
        "status": "success",
        "finished_at": time.time(),
        "session_id": "sess1",
        "encoded_repo": "proj-abc",
        "comment_count": 2,
        "severity": {"HIGH": 1, "MEDIUM": 0, "LOW": 0},
        "tokens": {"prompt": 1000, "completion": 50, "total": 1050, "llm_requests": 2},
        "high_preview": [{"file_path": "a.py", "line": 1, "snippet": "[HIGH] bug"}],
    }
    index_path.write_text(json.dumps(record) + "\n", encoding="utf-8")

    resp = client.get("/")
    assert resp.status_code == 200
    assert "group/demo" in resp.text
    assert "HIGH 告警" not in resp.text  # badge on repo page; index uses row-high class
    assert "5483" in resp.text


def test_repos_with_repo(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(tmp_path / "idx.jsonl"))
    repo = tmp_path / "proj-abc"
    jsonl = repo / "sess1.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_start", "sessionId": "sess1", "cwd": "/x/proj"}),
                json.dumps(
                    {
                        "type": "tool_call",
                        "tool_name": "code_comment",
                        "arguments": "[HIGH] critical",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resp = client.get("/repos")
    assert resp.status_code == 200
    assert "proj" in resp.text
    assert "5483" in resp.text


def test_mr_history(client, monkeypatch, tmp_path):
    index_path = tmp_path / "idx.jsonl"
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(index_path))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
    record = {
        "job_id": "j1",
        "project_id": "111",
        "project_path": "g/p",
        "mr_iid": "5",
        "status": "success",
        "finished_at": time.time(),
        "severity": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
        "tokens": {"total": 0, "prompt": 0, "completion": 0, "llm_requests": 0},
    }
    index_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
    resp = client.get("/mr/111/5")
    assert resp.status_code == 200
    assert "j1" in resp.text


def test_repo_slug_with_comma(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(tmp_path / "idx.jsonl"))
    repo = tmp_path / "group,proj,111"
    repo.mkdir(parents=True)
    (repo / "s1.jsonl").write_text(
        json.dumps({"type": "session_start", "sessionId": "s1", "cwd": "/x/demo"}) + "\n",
        encoding="utf-8",
    )
    resp = client.get("/r/group%2Cproj%2C111")
    assert resp.status_code == 200
    assert "demo" in resp.text


def test_repo_sessions_inline_comment_summary(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(tmp_path / "idx.jsonl"))
    repo = tmp_path / "proj-abc"
    jsonl = repo / "sess1.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_start", "sessionId": "sess1", "cwd": "/x/proj"}),
                json.dumps(
                    {
                        "type": "tool_call",
                        "tool_name": "code_comment",
                        "arguments": json.dumps(
                            {
                                "path": "src/main.py",
                                "line": 42,
                                "content": "[HIGH] Possible NPE when user is null",
                            }
                        ),
                    }
                ),
                json.dumps(
                    {
                        "type": "tool_call",
                        "tool_name": "code_comment",
                        "arguments": "[MEDIUM] Consider extracting helper",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resp = client.get("/r/proj-abc")
    assert resp.status_code == 200
    assert "Possible NPE" in resp.text
    assert "src/main.py" in resp.text
    assert "MEDIUM" in resp.text
    assert "session-summary" in resp.text


def test_path_traversal_rejected(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(tmp_path / "idx.jsonl"))
    resp = client.get("/r/..%2F..%2Fetc/sess1")
    assert resp.status_code == 404


def test_session_detail(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(tmp_path / "idx.jsonl"))
    repo = tmp_path / "proj-abc"
    jsonl = repo / "sess1.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_start", "sessionId": "sess1", "cwd": "/x/proj"}),
                json.dumps(
                    {
                        "type": "tool_call",
                        "tool_name": "code_comment",
                        "arguments": "[HIGH] NPE",
                    }
                ),
                json.dumps(
                    {
                        "type": "tool_call",
                        "tool_name": "code_comment",
                        "arguments": "[MEDIUM] style",
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resp = client.get("/r/proj-abc/sess1")
    assert resp.status_code == 200
    assert "NPE" in resp.text
    assert "官方详情" in resp.text
    assert "5483" in resp.text or "localhost:5483" in resp.text


def test_index_shows_latest_tokens_on_repos(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(tmp_path / "idx.jsonl"))
    repo = tmp_path / "proj-abc"
    jsonl = repo / "sess1.jsonl"
    jsonl.parent.mkdir(parents=True)
    jsonl.write_text(
        "\n".join(
            [
                json.dumps({"type": "session_start", "sessionId": "sess1", "cwd": "/x/proj"}),
                json.dumps(
                    {
                        "type": "llm_response",
                        "usage": {"prompt_tokens": 12_345, "completion_tokens": 678},
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resp = client.get("/repos")
    assert resp.status_code == 200
    assert "Latest Tokens" in resp.text
    assert "13K" in resp.text

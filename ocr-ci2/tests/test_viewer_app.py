"""Severity Dashboard HTTP 路由测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from viewer.app import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("SEVERITY_VIEWER_ALLOWED_HOSTS", "testserver")
    return TestClient(app)


def test_index_empty_sessions(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "No session data found" in resp.text


def test_index_with_repo(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
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

    resp = client.get("/")
    assert resp.status_code == 200
    assert "proj" in resp.text
    assert "HIGH 告警" in resp.text

    resp_high = client.get("/?highlight=high")
    assert resp_high.status_code == 200
    assert "proj" in resp_high.text


def test_repo_slug_with_comma(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
    repo = tmp_path / "group,proj,111"
    repo.mkdir(parents=True)
    (repo / "s1.jsonl").write_text(
        json.dumps({"type": "session_start", "sessionId": "s1", "cwd": "/x/demo"}) + "\n",
        encoding="utf-8",
    )
    resp = client.get("/r/group%2Cproj%2C111")
    assert resp.status_code == 200
    assert "demo" in resp.text


def test_path_traversal_rejected(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
    resp = client.get("/r/..%2F..%2Fetc/sess1")
    assert resp.status_code == 404


def test_session_detail(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
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
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    resp = client.get("/r/proj-abc/sess1")
    assert resp.status_code == 200
    assert "NPE" in resp.text
    assert "官方详情" in resp.text

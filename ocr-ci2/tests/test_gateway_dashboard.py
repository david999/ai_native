"""Gateway + Dashboard 共存测试。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway.main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_includes_dashboard(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data.get("dashboard") == "enabled"


def test_dashboard_index_empty(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(tmp_path / "empty.jsonl"))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path / "sessions"))
    resp = client.get("/")
    assert resp.status_code == 200
    assert "MR 评审流" in resp.text


def test_static_css(client):
    resp = client.get("/static/style.css")
    assert resp.status_code == 200
    assert "kpi-bar" in resp.text


def test_repos_page(client, monkeypatch, tmp_path):
    sessions = tmp_path / "sessions"
    repo = sessions / "proj-abc"
    repo.mkdir(parents=True)
    (repo / "s1.jsonl").write_text(
        json.dumps({"type": "session_start", "sessionId": "s1", "cwd": "/x/proj"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions))
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(tmp_path / "idx.jsonl"))
    resp = client.get("/repos")
    assert resp.status_code == 200
    assert "proj" in resp.text
    assert "5483" in resp.text or "官方" in resp.text

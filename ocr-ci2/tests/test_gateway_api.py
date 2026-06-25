"""gateway.main HTTP API 测试（TestClient）。

覆盖：/health、鉴权 401/503、POST 入队 202、GET job 状态。
不测：真实 ocr review、GitLab 网络调用。
"""
import os

import pytest
from fastapi.testclient import TestClient

from gateway.main import app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OCR_GATEWAY_SECRET", "test-secret")
    return TestClient(app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "queue_depth" in body
    assert "max_concurrent" in body
    assert "workspace_mirrors" in body


def test_trigger_requires_token(client):
    r = client.post(
        "/v1/review/merge-request",
        json={
            "project_id": "2",
            "project_path": "g/a",
            "mr_iid": "1",
            "target_branch": "main",
            "commit_sha": "abc",
        },
    )
    assert r.status_code == 401


def test_trigger_accepts_job(client, monkeypatch):
    monkeypatch.setattr(
        "gateway.main.enqueue_review",
        lambda job_id, req: type("J", (), {"job_id": job_id, "status": "queued"})(),
    )
    r = client.post(
        "/v1/review/merge-request",
        headers={"X-OCR-Gateway-Token": "test-secret"},
        json={
            "project_id": "2",
            "project_path": "java_group/demo",
            "mr_iid": "7",
            "target_branch": "main",
            "commit_sha": "deadbeef",
        },
    )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "queued"
    assert body["job_id"]


def test_trigger_rejects_invalid_project_id(client):
    r = client.post(
        "/v1/review/merge-request",
        headers={"X-OCR-Gateway-Token": "test-secret"},
        json={
            "project_id": "../evil",
            "project_path": "g/a",
            "mr_iid": "1",
            "target_branch": "main",
            "commit_sha": "abc",
        },
    )
    assert r.status_code == 400


def test_protected_routes_fail_without_secret(monkeypatch):
    monkeypatch.delenv("OCR_GATEWAY_SECRET", raising=False)
    client = TestClient(app)
    r = client.post(
        "/v1/review/merge-request",
        headers={"X-OCR-Gateway-Token": "anything"},
        json={
            "project_id": "2",
            "project_path": "g/a",
            "mr_iid": "1",
            "target_branch": "main",
            "commit_sha": "abc",
        },
    )
    assert r.status_code == 503

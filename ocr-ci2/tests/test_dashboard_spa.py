"""方案 C：Vue SPA Dashboard 开关与 API 扩展 smoke 测试。"""

from __future__ import annotations

import importlib
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SPA_DIST = ROOT / "viewer-spa" / "dist" / "index.html"


def _reload_app():
    """按当前环境变量重新加载 gateway.main（mount_dashboard 读 OCR_DASHBOARD_SPA）。"""
    import gateway.main as main_mod

    importlib.reload(main_mod)
    return main_mod.app


@pytest.fixture
def spa_dist_ready():
    if not SPA_DIST.is_file():
        pytest.skip("viewer-spa/dist not built; run: cd viewer-spa && npm run build")
    return SPA_DIST


def test_spa_mode_serves_index(spa_dist_ready, monkeypatch):
    monkeypatch.setenv("OCR_DASHBOARD_SPA", "1")
    app = _reload_app()
    client = TestClient(app)

    resp = client.get("/")
    assert resp.status_code == 200
    body = resp.text
    assert 'id="app"' in body or "id='app'" in body

    # API 不受 SPA 开关影响
    api = client.get("/api/health")
    assert api.status_code == 200
    assert api.json()["status"] == "ok"

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "ocr-gateway"


def test_spa_mode_legacy_htmx(spa_dist_ready, monkeypatch):
    monkeypatch.setenv("OCR_DASHBOARD_SPA", "1")
    app = _reload_app()
    client = TestClient(app)

    legacy = client.get("/legacy/")
    assert legacy.status_code == 200
    # 方案 A 工作台特征
    assert "评审" in legacy.text or "Dashboard" in legacy.text or "workbench" in legacy.text.lower() or "mr" in legacy.text.lower()


def test_spa_default_on_when_unset(spa_dist_ready, monkeypatch):
    """未设置 OCR_DASHBOARD_SPA 时默认启用 SPA。"""
    monkeypatch.delenv("OCR_DASHBOARD_SPA", raising=False)
    app = _reload_app()
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    assert 'id="app"' in resp.text or "id='app'" in resp.text


def test_htmx_fallback_when_spa_off(monkeypatch):
    monkeypatch.setenv("OCR_DASHBOARD_SPA", "0")
    app = _reload_app()
    client = TestClient(app)

    resp = client.get("/")
    assert resp.status_code == 200
    # 方案 A Jinja 模板，不是纯 Vite index
    assert "vite" not in resp.text.lower() or "app.js" in resp.text


def test_api_review_includes_issues(tmp_path, monkeypatch):
    """详情 API 应返回扁平 issues（方案 C 以 issue 为维度）。"""
    monkeypatch.delenv("OCR_DASHBOARD_SPA", raising=False)
    from tests.test_gateway_dashboard import _seed_index, _seed_session

    index = tmp_path / "review-index.jsonl"
    sessions = tmp_path / "sessions"
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(index))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions))
    _seed_index(index, job_id="job-spa-1")
    _seed_session(sessions)

    monkeypatch.setenv("OCR_DASHBOARD_SPA", "0")
    app = _reload_app()
    client = TestClient(app)

    resp = client.get("/api/reviews/job-spa-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["session"] is not None
    assert "issues" in data["session"]
    assert len(data["session"]["issues"]) >= 1
    assert "comments_by_file" in data["session"]


def test_api_repos_and_mr_endpoints(tmp_path, monkeypatch):
    from tests.test_gateway_dashboard import _seed_index, _seed_session

    index = tmp_path / "review-index.jsonl"
    sessions = tmp_path / "sessions"
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(index))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions))
    _seed_index(index, job_id="job-spa-2", project_id="9", mr_iid="7")
    _seed_session(sessions)

    monkeypatch.setenv("OCR_DASHBOARD_SPA", "0")
    app = _reload_app()
    client = TestClient(app)

    repos = client.get("/api/repos")
    assert repos.status_code == 200
    assert "items" in repos.json()

    repo = client.get("/api/repos/grp-proj-abc")
    assert repo.status_code == 200
    assert repo.json()["sessions"]

    sess = client.get("/api/repos/grp-proj-abc/sessions/sess-1")
    assert sess.status_code == 200
    assert sess.json()["session"]["issues"]

    mr = client.get("/api/mr/9/7")
    assert mr.status_code == 200
    assert mr.json()["reviews"]

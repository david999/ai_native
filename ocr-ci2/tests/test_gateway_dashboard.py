"""Gateway + Dashboard 共存测试（方案 A：双模式 Dashboard）。

覆盖：
- 历史兼容：/health、/、/repos、/static/style.css
- JSON API：/api/reviews、/api/reviews/{job_id}、/api/stats、/api/health
- 工作台 UI：/ 含 master-detail 与 app.js 引用；/stats 含统计页与 statsData
- Session 详情：评论按文件聚合渲染
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gateway.main import app


@pytest.fixture
def client():
    return TestClient(app)


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _seed_index(
    path: Path,
    *,
    job_id: str = "job-1",
    project_id: str = "1",
    project_path: str = "grp/proj",
    mr_iid: str = "42",
    high: int = 2,
    status: str = "success",
    ts: float | None = None,
) -> None:
    """追加一条 review-index.jsonl 记录（用 "a" 模式，支持同测试多次调用种多条）。"""
    from review_index import ReviewRecord

    record = ReviewRecord(
        job_id=job_id,
        project_id=project_id,
        project_path=project_path,
        mr_iid=mr_iid,
        target_branch="main",
        commit_sha="abcdef1234567890",
        status=status,
        message="ok" if status == "success" else "boom",
        finished_at=ts if ts is not None else time.time(),
        session_id="sess-1",
        encoded_repo="grp-proj-abc",
        comment_count=3,
        severity={"HIGH": high, "MEDIUM": 1, "LOW": 0},
        tokens={"prompt": 1000, "completion": 200, "total": 1200, "llm_requests": 3},
        high_preview=[{"file_path": "src/Foo.java", "line": 42, "snippet": "[HIGH] NPE"}],
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:  # 追加，避免二次调用覆盖前一条
        fh.write(json.dumps(record.to_dict(), ensure_ascii=False) + "\n")


def _seed_session(sessions_dir: Path, encoded_repo="grp-proj-abc", session_id="sess-1") -> Path:
    """写一个含 code_comment 事件的 session JSONL。"""
    jsonl = sessions_dir / encoded_repo / f"{session_id}.jsonl"
    _write_jsonl(
        jsonl,
        [
            {"type": "session_start", "sessionId": session_id, "cwd": "/work/proj", "gitBranch": "feat/x", "timestamp": "2026-07-15T10:00:00Z"},
            {
                "type": "tool_call",
                "tool_name": "code_comment",
                "arguments": json.dumps({"path": "src/Foo.java", "end_line": 42, "content": "[HIGH] NPE risk"}),
            },
            {
                "type": "tool_call",
                "tool_name": "code_comment",
                "arguments": json.dumps({"path": "src/Bar.java", "end_line": 7, "content": "[MEDIUM] naming"}),
            },
        ],
    )
    return jsonl


# ===== 历史兼容 =====


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
    assert "评审工作台" in resp.text


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


# ===== 方案 A：JSON API =====


def test_api_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_api_reviews_empty(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(tmp_path / "empty.jsonl"))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path / "sessions"))
    resp = client.get("/api/reviews")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["items"] == []
    assert payload["total"] == 0
    assert "kpis" in payload
    assert payload["has_mr_index"] is False
    assert "local_repos" in payload


def test_api_reviews_includes_local_repos_without_index(client, monkeypatch, tmp_path):
    """无 review-index 时仍返回本地 Session 仓库（与方案 A 工作台一致）。"""
    sessions = tmp_path / "sessions"
    repo = sessions / "grp-proj-abc"
    repo.mkdir(parents=True)
    (repo / "sess-1.jsonl").write_text(
        json.dumps({"type": "session_start", "sessionId": "sess-1", "cwd": "/work/proj"}) + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions))
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(tmp_path / "empty.jsonl"))
    resp = client.get("/api/reviews")
    payload = resp.json()
    assert payload["items"] == []
    assert len(payload["local_repos"]) == 1
    assert payload["local_repos"][0]["encoded_path"] == "grp-proj-abc"
    assert payload["local_repos"][0]["latest_session_id"] == "sess-1"


def test_api_local_repos_excludes_indexed_when_mr_filtered_out(client, monkeypatch, tmp_path):
    """筛选导致 MR 列表为空时，已索引仓库仍不应出现在 local_repos。"""
    idx = tmp_path / "idx.jsonl"
    sessions_dir = tmp_path / "sessions"
    # 索引仓：success、无 HIGH → highlight=failed 时会被滤掉
    _seed_index(idx, job_id="indexed", high=0, status="success")
    _seed_session(sessions_dir, encoded_repo="grp-proj-abc", session_id="sess-1")
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions_dir))

    payload = client.get("/api/reviews?highlight=failed").json()
    assert payload["items"] == []
    assert payload["local_repos"] == []


def test_api_local_repo_session_returns_issues(client, monkeypatch, tmp_path):
    """本地 Session 可通过 API 加载 issues（工作台内联联动依赖此接口）。"""
    idx = tmp_path / "idx.jsonl"
    sessions_dir = tmp_path / "sessions"
    _seed_session(sessions_dir, encoded_repo="orphan-repo", session_id="sess-x")
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions_dir))

    reviews = client.get("/api/reviews").json()
    local = next(r for r in reviews["local_repos"] if r["encoded_path"] == "orphan-repo")
    assert local["latest_session_id"] == "sess-x"

    detail = client.get(f"/api/repos/orphan-repo/sessions/sess-x").json()
    issues = detail["session"]["issues"]
    assert len(issues) >= 2
    assert any(i.get("level") == "HIGH" for i in issues)
    assert any(i.get("level") == "HIGH" for i in issues)


def test_workbench_local_repo_inline_attributes(client, monkeypatch, tmp_path):
    """方案 A：本地 Session 项带 data-session-id，供 app.js 内联加载。"""
    idx = tmp_path / "idx.jsonl"
    sessions_dir = tmp_path / "sessions"
    _seed_session(sessions_dir, encoded_repo="orphan-repo-xyz", session_id="sess-orphan")
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions_dir))
    # conftest 默认 OCR_DASHBOARD_SPA=0，工作台在 /
    resp = client.get("/")
    text = resp.text
    assert 'data-encoded-repo="orphan-repo-xyz"' in text
    assert 'data-session-id="sess-orphan"' in text
    assert 'href="/r/orphan-repo-xyz"' not in text.split("local-divider")[-1]


def test_api_reviews_returns_records_and_kpis(client, monkeypatch, tmp_path):
    idx = tmp_path / "idx.jsonl"
    _seed_index(idx, high=2)
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path / "sessions"))
    resp = client.get("/api/reviews")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    item = payload["items"][0]
    assert item["job_id"] == "job-1"
    assert item["high"] == 2
    assert item["mr_label"] == "!42"
    assert item["status_label"] == "已完成"
    assert payload["kpis"]["open_high"] >= 2


def test_api_reviews_filter_high_and_failed(client, monkeypatch, tmp_path):
    idx = tmp_path / "idx.jsonl"
    base = time.time()
    _seed_index(idx, job_id="ok", mr_iid="10", high=0, ts=base)                     # success，无 HIGH
    _seed_index(idx, job_id="bad", mr_iid="11", high=0, status="failed", ts=base + 1)  # failed
    _seed_index(idx, job_id="hot", mr_iid="12", high=2, ts=base + 2)                # success，有 HIGH
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path / "sessions"))

    all_resp = client.get("/api/reviews").json()
    assert all_resp["total"] == 3  # ok / bad / hot 三条不同 MR

    only_failed = client.get("/api/reviews?highlight=failed").json()
    ids = {i["job_id"] for i in only_failed["items"]}
    assert ids == {"bad"}  # 仅 failed；ok/hot 被排除
    assert "ok" not in ids and "hot" not in ids

    only_high = client.get("/api/reviews?highlight=high").json()
    high_ids = {i["job_id"] for i in only_high["items"]}
    # hot（success + HIGH）保留；bad（failed）按现有规则保留；ok（success 无 HIGH）排除
    assert "hot" in high_ids
    assert "ok" not in high_ids


def test_api_reviews_search_by_project_path(client, monkeypatch, tmp_path):
    idx = tmp_path / "idx.jsonl"
    _seed_index(idx, job_id="j-a", project_path="java_group/datacalc-web", mr_iid="1")
    _seed_index(idx, job_id="j-b", project_path="go_group/parser", mr_iid="2")
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path / "sessions"))

    resp = client.get("/api/reviews?q=datacalc").json()
    assert {i["job_id"] for i in resp["items"]} == {"j-a"}

    resp_go = client.get("/api/reviews?q=parser").json()
    assert {i["job_id"] for i in resp_go["items"]} == {"j-b"}


def test_api_reviews_pagination(client, monkeypatch, tmp_path):
    idx = tmp_path / "idx.jsonl"
    base = time.time()
    _seed_index(idx, job_id="p1", mr_iid="1", ts=base)
    _seed_index(idx, job_id="p2", mr_iid="2", ts=base + 1)
    _seed_index(idx, job_id="p3", mr_iid="3", ts=base + 2)
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path / "sessions"))

    page1 = client.get("/api/reviews?limit=2&offset=0").json()
    assert page1["total"] == 3
    assert len(page1["items"]) == 2
    # latest_per_mr 按 finished_at 降序，故首条为 p3
    assert page1["items"][0]["job_id"] == "p3"

    page2 = client.get("/api/reviews?limit=2&offset=2").json()
    assert len(page2["items"]) == 1
    assert page2["items"][0]["job_id"] == "p1"


def test_api_review_detail_with_session_comments_by_file(client, monkeypatch, tmp_path):
    idx = tmp_path / "idx.jsonl"
    _seed_index(idx, high=1)
    sessions_dir = tmp_path / "sessions"
    _seed_session(sessions_dir)
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions_dir))

    resp = client.get("/api/reviews/job-1")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["record"]["job_id"] == "job-1"
    session = payload["session"]
    assert session is not None
    # 按文件聚合：至少 2 个文件
    files = {f["file_path"] for f in session["comments_by_file"]}
    assert "src/Foo.java" in files
    assert "src/Bar.java" in files
    # Foo.java 含 HIGH，应排在最前
    assert session["comments_by_file"][0]["file_path"] == "src/Foo.java"
    assert session["comments_by_file"][0]["severity"]["HIGH"] == 1


def test_api_review_detail_404(client, monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(tmp_path / "empty.jsonl"))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path / "sessions"))
    resp = client.get("/api/reviews/missing")
    assert resp.status_code == 404


def test_api_stats_overview(client, monkeypatch, tmp_path):
    idx = tmp_path / "idx.jsonl"
    base = time.time()
    _seed_index(idx, job_id="j-a", project_path="grp/projA", mr_iid="1", high=1, ts=base)
    _seed_index(idx, job_id="j-b", project_path="grp/projB", mr_iid="2", high=3, ts=base + 1)
    _seed_index(idx, job_id="j-c", project_path="grp/projC", mr_iid="3", high=2, ts=base + 2)
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path / "sessions"))
    resp = client.get("/api/stats?days=7")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["days"] == 7
    assert len(payload["daily"]) == 7
    assert payload["kpis"]["open_high"] == 6  # 1 + 3 + 2
    # 今天应有 3 条评审
    assert payload["daily"][-1]["reviews"] == 3
    # project_high_top 按 high 降序：projB(3) > projC(2) > projA(1)
    top = payload["project_high_top"]
    assert [r["project_path"] for r in top] == ["grp/projB", "grp/projC", "grp/projA"]
    assert top[0]["high"] >= top[1]["high"] >= top[-1]["high"]


# ===== 方案 A：工作台 / 统计页 UI =====


def test_workbench_index_has_master_detail_and_appjs(client, monkeypatch, tmp_path):
    idx = tmp_path / "idx.jsonl"
    _seed_index(idx, high=1)
    sessions_dir = tmp_path / "sessions"
    _seed_session(sessions_dir)
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions_dir))
    resp = client.get("/")
    assert resp.status_code == 200
    text = resp.text
    assert "评审工作台" in text
    assert "master-detail" in text
    assert "mr-detail-panel" in text
    assert 'data-job-id="job-1"' in text
    assert "/static/app.js" in text
    # Tab 链接到统计页
    assert '/stats' in text
    # 已索引仓库（grp-proj-abc）不应在「本地 Session」区重复出现
    assert "local-divider" not in text or "grp-proj-abc" not in text.split("local-divider")[-1]


def test_workbench_shows_local_sessions_for_unindexed_repos(client, monkeypatch, tmp_path):
    idx = tmp_path / "idx.jsonl"
    # 索引里只有 grp/proj（encoded grp-proj-abc）
    _seed_index(idx, high=0)
    sessions_dir = tmp_path / "sessions"
    # 额外造一个未索引的仓库 session
    _seed_session(sessions_dir, encoded_repo="orphan-repo-xyz", session_id="sess-orphan")
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions_dir))
    resp = client.get("/")
    assert resp.status_code == 200
    text = resp.text
    # 未索引仓库应并入左栏「本地 Session」区
    assert "local-divider" in text
    assert "orphan-repo-xyz" in text or "orphan" in text
    # 已索引仓库 grp-proj-abc 不应出现在本地 Session 区
    local_section = text.split("local-divider")[-1]
    assert "grp-proj-abc" not in local_section


def test_stats_page_renders_charts_and_tables(client, monkeypatch, tmp_path):
    idx = tmp_path / "idx.jsonl"
    _seed_index(idx, high=2)
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path / "sessions"))
    resp = client.get("/stats?days=14")
    assert resp.status_code == 200
    text = resp.text
    assert "统计概览" in text
    assert "chartReviews" in text
    assert "statsData" in text
    assert "项目 HIGH Top5" in text
    # 天数切换链接
    assert "/stats?days=30" in text


def test_session_detail_renders_file_tree(client, monkeypatch, tmp_path):
    idx = tmp_path / "idx.jsonl"
    _seed_index(idx, high=1)
    sessions_dir = tmp_path / "sessions"
    _seed_session(sessions_dir)
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(idx))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions_dir))
    resp = client.get("/r/grp-proj-abc/sess-1")
    assert resp.status_code == 200
    text = resp.text
    assert "file-tree" in text
    assert "src/Foo.java" in text
    assert "src/Bar.java" in text


# ===== 可选 Basic Auth =====


def test_basic_auth_protects_dashboard_when_configured(monkeypatch, tmp_path):
    monkeypatch.setenv("OCR_REVIEW_INDEX_PATH", str(tmp_path / "empty.jsonl"))
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path / "sessions"))
    monkeypatch.setenv("OCR_DASHBOARD_USER", "admin")
    monkeypatch.setenv("OCR_DASHBOARD_PASSWORD", "secret")

    import viewer.routes as routes_mod
    from fastapi import FastAPI

    # 用独立 app 验证 env 触发的 Basic Auth（不手动重复挂中间件）
    guarded = FastAPI()

    @guarded.get("/health")
    def _health():
        return {"status": "ok"}

    # mount_dashboard 内部会读取 env 并挂 BasicAuthMiddleware
    routes_mod.mount_dashboard(guarded)
    guarded_client = TestClient(guarded)

    # 未带凭证访问受保护端点 → 401
    no_auth = guarded_client.get("/api/health")
    assert no_auth.status_code == 401
    assert "WWW-Authenticate" in no_auth.headers

    # 带正确凭证 → 200
    with_auth = guarded_client.get("/api/health", auth=("admin", "secret"))
    assert with_auth.status_code == 200

    # 错误凭证 → 401
    wrong = guarded_client.get("/api/health", auth=("admin", "wrong"))
    assert wrong.status_code == 401

    # /health 在放行前缀中，不应被 Basic Auth 拦截
    health = guarded_client.get("/health")
    assert health.status_code == 200

    # /static/* 也应受 Basic Auth 保护
    static_resp = guarded_client.get("/static/style.css")
    assert static_resp.status_code == 401
    static_ok = guarded_client.get("/static/style.css", auth=("admin", "secret"))
    assert static_ok.status_code == 200

    monkeypatch.delenv("OCR_DASHBOARD_USER", raising=False)
    monkeypatch.delenv("OCR_DASHBOARD_PASSWORD", raising=False)

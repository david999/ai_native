"""OCR Gateway Dashboard JSON API（方案 A/C 共用数据层）。

端点（与 Dashboard HTML 同端口 :8010）：

- ``GET /api/reviews``                              MR 评审列表 + KPI + local_repos
- ``GET /api/reviews/{job_id}``                     单条评审详情（含 issues / comments_by_file）
- ``GET /api/stats``                                统计概览
- ``GET /api/repos``                                本地 Session 仓库列表
- ``GET /api/repos/{encoded_repo}``                 仓库 Session 列表
- ``GET /api/repos/{encoded_repo}/sessions/{id}``   Session 详情
- ``GET /api/mr/{project_id}/{mr_iid}``             MR 历史评审
- ``GET /api/health``                               API 探活

数据源仍是 review-index.jsonl + session JSONL，本迭代不引入 DB。
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from review_index import (  # noqa: E402
    ReviewRecord,
    compute_kpis,
    compute_stats_overview,
    find_record_by_job_id,
    finished_at_datetime,
    latest_per_mr,
    list_sessions_for_mr,
    load_all_records,
    mr_web_url,
)
from session_telemetry import (  # noqa: E402
    comment_to_dict,
    discover_repos,
    format_token_count,
    group_comments_by_file,
    list_repo_sessions,
    load_session,
    official_viewer_url,
    sessions_root,
)
from viewer.job_status import enrich_status_fields  # noqa: E402

# 默认分页与统计窗口
DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def _record_summary(record: ReviewRecord) -> dict:
    """列表用精简字段（与 HTML 表格保持一致的命名，便于前后端复用）。"""
    return enrich_status_fields(
        {
            "job_id": record.job_id,
            "project_id": record.project_id,
            "project_path": record.project_path,
            "mr_iid": record.mr_iid,
            "mr_label": f"!{record.mr_iid}",
            "mr_url": record.gitlab_mr_url,
            "target_branch": record.target_branch,
            "commit_short": (record.commit_sha or "")[:8] or "—",
            "status": record.status,
            "message": record.message,
            "finished_at": finished_at_datetime(record).isoformat() if record.finished_at else None,
            "high": int(record.severity.get("HIGH", 0)),
            "medium": int(record.severity.get("MEDIUM", 0)),
            "low": int(record.severity.get("LOW", 0)),
            "comment_count": int(record.comment_count or 0),
            "total_tokens": int(record.tokens.get("total", 0)),
            "total_tokens_fmt": format_token_count(int(record.tokens.get("total", 0))),
            "has_high": record.has_high,
            "session_id": record.session_id,
            "encoded_repo": record.encoded_repo,
            # 深链接（保持与现有 HTML 路由兼容）
            "mr_history_url": f"/mr/{quote(record.project_id, safe='')}/{quote(record.mr_iid, safe='')}",
            "session_url": record.session_dashboard_url(),
            "official_url": record.official_viewer_url(),
        }
    )


def _running_job_summary(job) -> dict:
    """运行中 job（仅内存态）转成与 _record_summary 兼容的 dict。"""
    return enrich_status_fields(
        {
            "job_id": job.job_id,
            "project_id": job.project_id,
            "project_path": job.project_path,
            "mr_iid": job.mr_iid,
            "mr_label": f"!{job.mr_iid}",
            "mr_url": mr_web_url(job.project_path, job.mr_iid),
            "target_branch": job.target_branch,
            "commit_short": (job.commit_sha or "")[:8] or "—",
            "status": job.status,
            "message": job.message,
            "finished_at": None,
            "high": 0,
            "medium": 0,
            "low": 0,
            "comment_count": 0,
            "total_tokens": 0,
            "total_tokens_fmt": "—",
            "has_high": False,
            "session_id": "",
            "encoded_repo": "",
            "mr_history_url": f"/mr/{quote(job.project_id, safe='')}/{quote(job.mr_iid, safe='')}",
            "session_url": "",
            "official_url": official_viewer_url(),
        }
    )


def _merge_running_jobs(rows: list[dict]) -> list[dict]:
    """把内存中的运行中/排队中 job 合并到列表顶部（重启后会丢失，符合现有行为）。"""
    try:
        from gateway.review_service import list_active_jobs
    except ImportError:
        return rows

    existing_keys = {(r["project_id"], r["mr_iid"]) for r in rows}
    merged = list(rows)
    for job in list_active_jobs():
        if (job.project_id, job.mr_iid) in existing_keys:
            continue
        merged.insert(0, _running_job_summary(job))
    return merged


def _filter_rows(
    rows: list[dict],
    *,
    query: str,
    only_high: bool,
    only_failed: bool,
) -> list[dict]:
    """按项目路径搜索 / 仅 HIGH / 仅 failed 过滤。"""
    filtered = []
    for row in rows:
        if only_high and not row["has_high"] and row["status"] == "success":
            continue
        if only_failed and row["status"] != "failed":
            continue
        if query and query not in row["project_path"].lower():
            continue
        filtered.append(row)
    return filtered


def _queue_depth() -> int:
    """安全获取队列深度（gateway 不可导入时返回 0）。"""
    try:
        from gateway.review_service import queue_depth

        return queue_depth()
    except ImportError:
        return 0


def local_repo_summary(repo) -> dict:
    """序列化本地 Session 仓库摘要（含最新 session_id，供工作台内联加载 issues）。"""
    return {
        "encoded_path": repo.encoded_path,
        "display_name": repo.display_name,
        "session_count": repo.session_count,
        "high": repo.latest_severity.high,
        "medium": repo.latest_severity.medium,
        "low": repo.latest_severity.low,
        "latest_tokens": repo.latest_tokens.total,
        "latest_tokens_fmt": format_token_count(repo.latest_tokens.total),
        "last_modified": repo.last_modified.isoformat() if repo.last_modified else None,
        "has_high": repo.latest_has_high,
        "latest_session_id": repo.latest_session_id,
        "repo_url": f"/r/{quote(repo.encoded_path, safe='')}",
    }


def _local_repos_for_rows(rows: list[dict], *, indexed_repos: set[str] | None = None) -> list[dict]:
    """与方案 A index.html 一致：展示未出现在 Gateway 索引中的本地 Session 仓库。

    indexed_repos 必须来自**未筛选**的全量 MR 列表；若用筛选后的 rows 推断，
    会把已索引仓库误放进「本地 Session」区（例如 highlight=failed 时）。
    """
    indexed = indexed_repos if indexed_repos is not None else {
        r.get("encoded_repo") for r in rows if r.get("encoded_repo")
    }
    local: list[dict] = []
    for repo in discover_repos():
        if repo.encoded_path in indexed:
            continue
        local.append(local_repo_summary(repo))
    return local


# JSON API 路由：单独的 router，由 viewer.routes.mount_dashboard 挂载
api_router = APIRouter(prefix="/api", include_in_schema=True, tags=["dashboard"])


@api_router.get("/reviews")
def list_reviews(
    q: str = Query("", description="按项目路径过滤（大小写不敏感）"),
    highlight: str = Query("", description="high | failed"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT, description="返回条数上限"),
    offset: int = Query(0, ge=0, description="偏移量"),
):
    """MR 评审列表（每个 MR 取最新一条）+ 运行中 job + KPI。"""
    records = load_all_records()
    latest = latest_per_mr(records)
    rows = [_record_summary(r) for r in latest]
    rows = _merge_running_jobs(rows)
    # 已索引仓库集合用全量 rows，避免筛选后把索引仓误判为「本地 Session」
    indexed_repos = {r.get("encoded_repo") for r in rows if r.get("encoded_repo")}

    only_high = highlight.lower() in ("high", "1", "true", "yes")
    only_failed = highlight.lower() in ("failed", "fail")
    query = q.strip().lower()
    filtered = _filter_rows(rows, query=query, only_high=only_high, only_failed=only_failed)

    total = len(filtered)
    page = filtered[offset : offset + limit]
    kpis = compute_kpis(records, queue_depth=_queue_depth())

    return {
        "items": page,
        "total": total,
        "limit": limit,
        "offset": offset,
        "filters": {"q": q, "highlight": highlight},
        "kpis": kpis,
        # 与方案 A 工作台一致：无 Gateway MR 索引时仍可浏览本地 Session
        "local_repos": _local_repos_for_rows(filtered, indexed_repos=indexed_repos),
        "has_mr_index": bool(records),
    }


def _session_payload_from_telemetry(session) -> dict:
    """把 SessionTelemetry 序列化为 API payload（含扁平 issues）。"""
    comments_by_level = {"HIGH": [], "MEDIUM": [], "LOW": []}
    issues: list[dict] = []
    for comment in session.all_comments:
        item = comment_to_dict(comment)
        level = comment.level if comment.level in comments_by_level else "LOW"
        comments_by_level[level].append(item)
        issues.append(item)

    level_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    issues.sort(
        key=lambda c: (
            level_rank.get(c.get("level", "LOW"), 9),
            c.get("file_path") or "",
            int(c.get("line") or 0),
        )
    )

    return {
        "session_id": session.session_id,
        "encoded_repo": session.repo_slug,
        "cwd": session.cwd,
        "git_branch": session.git_branch,
        "files_reviewed": session.files_reviewed,
        "duration_seconds": session.duration_seconds,
        "llm_failures": session.llm_failures,
        "tool_counts": session.tool_counts,
        "tokens": {
            "prompt": session.tokens.prompt_tokens,
            "completion": session.tokens.completion_tokens,
            "total": session.tokens.total,
            "cache_read": session.tokens.cache_read_tokens,
            "llm_requests": session.tokens.request_count,
        },
        "severity": session.severity.to_dict(),
        "comments_by_file": group_comments_by_file(session.all_comments),
        "comments_by_level": comments_by_level,
        "issues": issues,
        "comment_total": len(session.all_comments),
        "official_url": session.official_viewer_url(),
    }


def _session_payload(record: ReviewRecord) -> dict | None:
    """加载并序列化对应 session 的评论（按文件 + 按级别 + 扁平 issues）。找不到返回 None。"""
    if not (record.encoded_repo and record.session_id):
        return None
    session = load_session(sessions_root(), record.encoded_repo, record.session_id)
    if session is None:
        return None
    return _session_payload_from_telemetry(session)


@api_router.get("/reviews/{job_id}")
def review_detail(job_id: str):
    """单条评审详情：record + session 评论（按文件聚合）+ MR 上下文。"""
    record = find_record_by_job_id(job_id)
    if record is None:
        raise HTTPException(status_code=404, detail="review not found")

    return {
        "record": _record_summary(record),
        "session": _session_payload(record),
    }


@api_router.get("/stats")
def stats_overview(
    days: int = Query(30, ge=1, le=90, description="趋势窗口天数（1–90）"),
):
    """统计概览：KPI + 每日评审量/HIGH/Token 中位数 + 项目 HIGH Top5。"""
    records = load_all_records()
    payload = compute_stats_overview(records, days=days, queue_depth=_queue_depth())
    payload["has_mr_index"] = bool(records)
    return payload


@api_router.get("/health")
def api_health() -> dict:
    """Dashboard API 健康检查（轻量，便于前端探活/轮询）。"""
    return {
        "status": "ok",
        "service": "ocr-gateway-dashboard-api",
        "now": datetime.now(tz=timezone.utc).isoformat(),
    }


@api_router.get("/repos")
def list_repos(highlight: str = Query("", description="high")):
    """本地 Session 仓库列表（供 SPA /repos）。"""
    only_high = highlight.lower() in ("high", "1", "true", "yes")
    items = []
    for repo in discover_repos():
        if only_high and not repo.latest_has_high:
            continue
        items.append(
            {
                "encoded_path": repo.encoded_path,
                "display_name": repo.display_name,
                "session_count": repo.session_count,
                "high": repo.latest_severity.high,
                "medium": repo.latest_severity.medium,
                "low": repo.latest_severity.low,
                "latest_tokens": repo.latest_tokens.total,
                "latest_tokens_fmt": format_token_count(repo.latest_tokens.total),
                "last_modified": repo.last_modified.isoformat() if repo.last_modified else None,
                "has_high": repo.latest_has_high,
                "repo_url": f"/r/{quote(repo.encoded_path, safe='')}",
            }
        )
    return {"items": items, "total": len(items)}


@api_router.get("/repos/{encoded_repo}")
def repo_detail(encoded_repo: str, highlight: str = Query("")):
    """某仓库下的 Session 列表。"""
    sessions = list_repo_sessions(sessions_root(), encoded_repo)
    if not sessions:
        raise HTTPException(status_code=404, detail="Repository not found or has no sessions")
    only_high = highlight.lower() in ("high", "1", "true", "yes")
    display_name = Path(sessions[0].cwd).name if sessions[0].cwd else encoded_repo
    rows = []
    for session in sessions:
        if only_high and not session.has_high:
            continue
        rows.append(
            {
                "session_id": session.session_id,
                "git_branch": session.git_branch,
                "timestamp": session.timestamp,
                "last_modified": session.last_modified.isoformat() if session.last_modified else None,
                "high": session.severity.high,
                "medium": session.severity.medium,
                "low": session.severity.low,
                "total_tokens": session.tokens.total,
                "total_tokens_fmt": format_token_count(session.tokens.total),
                "files_reviewed": session.files_reviewed,
                "has_high": session.has_high,
                "official_url": session.official_viewer_url(),
                "session_url": f"/r/{quote(encoded_repo, safe='')}/{quote(session.session_id, safe='')}",
            }
        )
    return {
        "encoded_repo": encoded_repo,
        "display_name": display_name,
        "sessions": rows,
    }


@api_router.get("/repos/{encoded_repo}/sessions/{session_id}")
def session_detail_api(encoded_repo: str, session_id: str):
    """Session 详情：扁平 issues + 按文件聚合（供 SPA Session 页）。"""
    session = load_session(sessions_root(), encoded_repo, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    mr_record = None
    for record in load_all_records():
        if record.session_id == session_id and record.encoded_repo == encoded_repo:
            mr_record = record
            break

    display_name = Path(session.cwd).name if session.cwd else encoded_repo
    return {
        "display_name": display_name,
        "session": _session_payload_from_telemetry(session),
        "record": _record_summary(mr_record) if mr_record else None,
        "mr_url": mr_record.gitlab_mr_url if mr_record else "",
    }


@api_router.get("/mr/{project_id}/{mr_iid}")
def mr_history_api(project_id: str, mr_iid: str):
    """同一 MR 的历史评审列表。"""
    records = list_sessions_for_mr(project_id, mr_iid)
    if not records:
        raise HTTPException(status_code=404, detail="No reviews found for this MR")
    reviews = []
    for idx, record in enumerate(records):
        row = _record_summary(record)
        row["is_latest"] = idx == 0
        reviews.append(row)
    sample = records[0]
    return {
        "project_id": project_id,
        "project_path": sample.project_path,
        "mr_iid": mr_iid,
        "mr_url": sample.gitlab_mr_url,
        "reviews": reviews,
    }

"""OCR Gateway Dashboard routes (HTML UI on :8010)."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from review_index import (  # noqa: E402
    ReviewRecord,
    compute_kpis,
    finished_at_datetime,
    list_mr_latest_reviews,
    list_sessions_for_mr,
    load_all_records,
    mr_web_url,
)
from session_telemetry import (  # noqa: E402
    discover_repos,
    format_token_count,
    list_repo_sessions,
    load_session,
    official_viewer_url,
    sessions_root,
)

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_STATIC_DIR = Path(__file__).resolve().parent / "static"

templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))
templates.env.filters["format_time"] = lambda value: _format_time(value)
templates.env.filters["format_tokens"] = format_token_count
templates.env.filters["urlquote_path"] = lambda value: quote(str(value), safe="")


def _format_time(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is not None:
        value = value.replace(tzinfo=None)
    return value.strftime("%Y-%m-%d %H:%M:%S")


def _repo_url(encoded_path: str) -> str:
    return f"/r/{quote(encoded_path, safe='')}"


def _repo_display_name(encoded_path: str, sessions) -> str:
    for session in sessions:
        if session.cwd:
            return Path(session.cwd).name or encoded_path
    return encoded_path


def _truthy_query(value: str) -> bool:
    return value.lower() in ("high", "1", "true", "yes", "failed")


def _comment_previews(session, *, limit: int = 5) -> tuple[list[dict], int]:
    """Return up to *limit* comment snippets for list views (HIGH first)."""
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    comments = sorted(
        session.all_comments,
        key=lambda c: (order.get(c.level, 9), c.file_path, c.line),
    )
    total = len(comments)
    previews: list[dict] = []
    for comment in comments[:limit]:
        snippet = comment.snippet.strip()
        if len(snippet) > 180:
            snippet = snippet[:177] + "..."
        previews.append(
            {
                "level": comment.level,
                "file_path": comment.file_path,
                "line": comment.line,
                "snippet": snippet,
            }
        )
    return previews, total


def _base_context(**extra):
    return {
        "official_viewer_url": official_viewer_url(),
        "sessions_root": str(sessions_root()),
        **extra,
    }


def _record_row(record: ReviewRecord) -> dict:
    return {
        "job_id": record.job_id,
        "project_id": record.project_id,
        "project_path": record.project_path,
        "mr_iid": record.mr_iid,
        "mr_label": f"!{record.mr_iid}",
        "mr_url": record.gitlab_mr_url,
        "mr_history_url": f"/mr/{quote(record.project_id, safe='')}/{quote(record.mr_iid, safe='')}",
        "target_branch": record.target_branch,
        "commit_short": (record.commit_sha or "")[:8] or "—",
        "status": record.status,
        "message": record.message,
        "finished_at": finished_at_datetime(record),
        "high": int(record.severity.get("HIGH", 0)),
        "medium": int(record.severity.get("MEDIUM", 0)),
        "low": int(record.severity.get("LOW", 0)),
        "comment_count": record.comment_count,
        "total_tokens": int(record.tokens.get("total", 0)),
        "total_tokens_fmt": format_token_count(int(record.tokens.get("total", 0))),
        "high_preview": record.high_preview,
        "has_high": record.has_high,
        "session_id": record.session_id,
        "encoded_repo": record.encoded_repo,
        "session_url": record.session_dashboard_url(),
        "official_url": record.official_viewer_url(),
    }


def _merge_running_jobs(rows: list[dict]) -> list[dict]:
    try:
        from gateway.review_service import list_active_jobs
    except ImportError:
        return rows

    existing_keys = {(r["project_id"], r["mr_iid"]) for r in rows}
    for job in list_active_jobs():
        key = (job.project_id, job.mr_iid)
        if key in existing_keys:
            continue
        rows.insert(
            0,
            {
                "job_id": job.job_id,
                "project_id": job.project_id,
                "project_path": job.project_path,
                "mr_iid": job.mr_iid,
                "mr_label": f"!{job.mr_iid}",
                "mr_url": mr_web_url(job.project_path, job.mr_iid),
                "mr_history_url": f"/mr/{quote(job.project_id, safe='')}/{quote(job.mr_iid, safe='')}",
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
                "high_preview": [],
                "has_high": False,
                "session_id": "",
                "encoded_repo": "",
                "session_url": "",
                "official_url": official_viewer_url(),
            },
        )
    return rows


router = APIRouter(include_in_schema=False)


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    highlight: str = Query("", description="high | failed"),
    q: str = Query("", description="project path filter"),
):
    from gateway.review_service import queue_depth

    all_records = load_all_records()
    latest = list_mr_latest_reviews()
    rows = [_record_row(r) for r in latest]
    rows = _merge_running_jobs(rows)

    only_high = highlight.lower() in ("high", "1", "true", "yes")
    only_failed = highlight.lower() in ("failed", "fail")
    query = q.strip().lower()

    filtered = []
    for row in rows:
        if only_high and not row["has_high"] and row["status"] == "success":
            continue
        if only_failed and row["status"] != "failed":
            continue
        if query and query not in row["project_path"].lower():
            continue
        filtered.append(row)

    kpis = compute_kpis(all_records, queue_depth=queue_depth())

    local_repos = []
    indexed_keys = {(r["project_id"], r["mr_iid"]) for r in rows if r.get("session_id")}
    for repo in discover_repos():
        local_repos.append(
            {
                "encoded_path": repo.encoded_path,
                "repo_url": _repo_url(repo.encoded_path),
                "display_name": repo.display_name,
                "session_count": repo.session_count,
                "high": repo.latest_severity.high,
                "medium": repo.latest_severity.medium,
                "low": repo.latest_severity.low,
                "latest_tokens": repo.latest_tokens.total,
                "last_modified": repo.last_modified,
                "has_high": repo.latest_has_high,
            }
        )

    return templates.TemplateResponse(
        request,
        "index.html",
        _base_context(
            mr_rows=filtered,
            local_repos=local_repos,
            kpis=kpis,
            only_high=only_high,
            only_failed=only_failed,
            query=q,
        ),
    )


@router.get("/repos", response_class=HTMLResponse)
async def repos_list(
    request: Request,
    highlight: str = Query(""),
):
    only_high = _truthy_query(highlight)
    rows = []
    for repo in discover_repos():
        if only_high and not repo.latest_has_high:
            continue
        latest_session = list_repo_sessions(sessions_root(), repo.encoded_path)
        latest_official = latest_session[0].official_viewer_url() if latest_session else official_viewer_url()
        rows.append(
            {
                "encoded_path": repo.encoded_path,
                "repo_url": _repo_url(repo.encoded_path),
                "display_name": repo.display_name,
                "session_count": repo.session_count,
                "high": repo.latest_severity.high,
                "medium": repo.latest_severity.medium,
                "low": repo.latest_severity.low,
                "latest_tokens": repo.latest_tokens.total,
                "last_modified": repo.last_modified,
                "has_high": repo.latest_has_high,
                "official_url": latest_official,
            }
        )

    return templates.TemplateResponse(
        request,
        "repos.html",
        _base_context(repos=rows, only_high=only_high),
    )


@router.get("/mr/{project_id}/{mr_iid}", response_class=HTMLResponse)
async def mr_history(request: Request, project_id: str, mr_iid: str):
    records = list_sessions_for_mr(project_id, mr_iid)
    if not records:
        raise HTTPException(status_code=404, detail="No reviews found for this MR")

    rows = []
    for idx, record in enumerate(records):
        row = _record_row(record)
        row["is_latest"] = idx == 0
        rows.append(row)

    sample = records[0]
    return templates.TemplateResponse(
        request,
        "mr.html",
        _base_context(
            project_id=project_id,
            project_path=sample.project_path,
            mr_iid=mr_iid,
            mr_url=sample.gitlab_mr_url,
            reviews=rows,
        ),
    )


@router.get("/r/{encoded_repo}", response_class=HTMLResponse)
async def repo_sessions(
    request: Request,
    encoded_repo: str,
    highlight: str = Query(""),
):
    root = sessions_root()
    sessions = list_repo_sessions(root, encoded_repo)
    if not sessions:
        raise HTTPException(status_code=404, detail="Repository not found or has no sessions")

    only_high = _truthy_query(highlight)
    display_name = _repo_display_name(encoded_repo, sessions)

    rows = []
    for session in sessions:
        if only_high and not session.has_high:
            continue
        comment_previews, comment_total = _comment_previews(session)
        rows.append(
            {
                "session_id": session.session_id,
                "session_url": f"{_repo_url(encoded_repo)}/{quote(session.session_id, safe='')}",
                "git_branch": session.git_branch,
                "timestamp": session.timestamp,
                "last_modified": session.last_modified,
                "high": session.severity.high,
                "medium": session.severity.medium,
                "low": session.severity.low,
                "total_tokens": session.tokens.total,
                "prompt_tokens": session.tokens.prompt_tokens,
                "completion_tokens": session.tokens.completion_tokens,
                "llm_requests": session.tokens.request_count,
                "files_reviewed": session.files_reviewed,
                "has_high": session.has_high,
                "official_url": session.official_viewer_url(),
                "comment_previews": comment_previews,
                "comment_total": comment_total,
                "comment_more": max(0, comment_total - len(comment_previews)),
            }
        )

    return templates.TemplateResponse(
        request,
        "repo.html",
        _base_context(
            encoded_repo=encoded_repo,
            repo_url=_repo_url(encoded_repo),
            display_name=display_name,
            sessions=rows,
            only_high=only_high,
            has_any_sessions=bool(sessions),
        ),
    )


@router.get("/r/{encoded_repo}/{session_id}", response_class=HTMLResponse)
async def session_detail(request: Request, encoded_repo: str, session_id: str):
    root = sessions_root()
    session = load_session(root, encoded_repo, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    display_name = Path(session.cwd).name if session.cwd else encoded_repo

    mr_record = None
    for record in load_all_records():
        if record.session_id == session_id and record.encoded_repo == encoded_repo:
            mr_record = record
            break

    comments_by_level = {"HIGH": [], "MEDIUM": [], "LOW": []}
    for comment in session.all_comments:
        level = comment.level if comment.level in comments_by_level else "LOW"
        comments_by_level[level].append(comment)

    return templates.TemplateResponse(
        request,
        "session.html",
        _base_context(
            session=session,
            encoded_repo=encoded_repo,
            repo_url=_repo_url(encoded_repo),
            display_name=display_name,
            official_url=session.official_viewer_url(),
            high_comments=session.high_comments,
            comments_by_level=comments_by_level,
            mr_record=mr_record,
        ),
    )


def mount_dashboard(app) -> None:
    """Attach Dashboard static files and HTML routes to the Gateway app."""
    if _STATIC_DIR.is_dir():
        app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")
    app.include_router(router)

    if os.environ.get("OCR_GATEWAY_DASHBOARD_HOST_GUARD", "").lower() in ("1", "true", "yes"):
        from viewer.hostguard import HostGuardMiddleware

        bind_host = os.environ.get("OCR_GATEWAY_DASHBOARD_BIND_HOST", "127.0.0.1")
        app.add_middleware(HostGuardMiddleware, bind_host=bind_host)

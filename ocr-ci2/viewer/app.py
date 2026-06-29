"""Severity Dashboard — FastAPI app on :5484 (reads OCR session JSONL)."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from session_telemetry import (  # noqa: E402
    discover_repos,
    format_token_count,
    list_repo_sessions,
    load_session,
    official_viewer_url,
    sessions_root,
)
from viewer.hostguard import HostGuardMiddleware  # noqa: E402

_TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_STATIC_DIR = Path(__file__).resolve().parent / "static"
_BIND_HOST = os.environ.get("SEVERITY_VIEWER_HOST", "127.0.0.1")

app = FastAPI(title="OCR Severity Dashboard", docs_url=None, redoc_url=None)
app.add_middleware(HostGuardMiddleware, bind_host=_BIND_HOST)
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


def _format_time(value: datetime | None) -> str:
    if value is None:
        return "—"
    if value.tzinfo is None:
        value = value.replace(tzinfo=None)
    return value.strftime("%Y-%m-%d %H:%M:%S")


templates.env.filters["format_time"] = _format_time
templates.env.filters["format_tokens"] = format_token_count
templates.env.filters["urlquote_path"] = lambda value: quote(str(value), safe="")


def _repo_url(encoded_path: str) -> str:
    return f"/r/{quote(encoded_path, safe='')}"


def _repo_display_name(encoded_path: str, sessions) -> str:
    for session in sessions:
        if session.cwd:
            return Path(session.cwd).name or encoded_path
    return encoded_path


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    highlight: str = Query("", description="high = only repos with HIGH severity"),
):
    root = sessions_root()
    repos = discover_repos(root)
    only_high = highlight.lower() in ("high", "1", "true", "yes")

    rows = []
    for repo in repos:
        if only_high and not repo.has_high:
            continue
        rows.append(
            {
                "encoded_path": repo.encoded_path,
                "repo_url": _repo_url(repo.encoded_path),
                "display_name": repo.display_name,
                "session_count": repo.session_count,
                "high": repo.severity.high,
                "medium": repo.severity.medium,
                "low": repo.severity.low,
                "latest_tokens": repo.latest_tokens.total,
                "latest_tokens_raw": repo.latest_tokens.total,
                "last_modified": repo.last_modified,
                "has_high": repo.has_high,
            }
        )

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "repos": rows,
            "only_high": only_high,
            "official_viewer_url": official_viewer_url(),
            "sessions_root": str(root),
        },
    )


@app.get("/r/{encoded_repo}", response_class=HTMLResponse)
async def repo_sessions(
    request: Request,
    encoded_repo: str,
    highlight: str = Query(""),
):
    root = sessions_root()
    sessions = list_repo_sessions(root, encoded_repo)
    if not sessions:
        raise HTTPException(status_code=404, detail="Repository not found or has no sessions")

    only_high = highlight.lower() in ("high", "1", "true", "yes")
    display_name = _repo_display_name(encoded_repo, sessions)

    rows = []
    for session in sessions:
        if only_high and not session.has_high:
            continue
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
                "has_high": session.has_high,
                "official_url": session.official_viewer_url(),
            }
        )

    return templates.TemplateResponse(
        request,
        "repo.html",
        {
            "encoded_repo": encoded_repo,
            "repo_url": _repo_url(encoded_repo),
            "display_name": display_name,
            "sessions": rows,
            "only_high": only_high,
            "official_viewer_url": official_viewer_url(),
            "has_any_sessions": bool(sessions),
        },
    )


@app.get("/r/{encoded_repo}/{session_id}", response_class=HTMLResponse)
async def session_detail(request: Request, encoded_repo: str, session_id: str):
    root = sessions_root()
    session = load_session(root, encoded_repo, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")

    display_name = Path(session.cwd).name if session.cwd else encoded_repo

    return templates.TemplateResponse(
        request,
        "session.html",
        {
            "session": session,
            "encoded_repo": encoded_repo,
            "repo_url": _repo_url(encoded_repo),
            "display_name": display_name,
            "official_url": session.official_viewer_url(),
            "high_comments": session.high_comments,
        },
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="OCR Severity Dashboard")
    parser.add_argument("--host", default=os.environ.get("SEVERITY_VIEWER_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("SEVERITY_VIEWER_PORT", "5484")),
    )
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()

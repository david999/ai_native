"""Persistent MR review index written by OCR Gateway."""

from __future__ import annotations

import json
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from session_telemetry import SeverityCounts, TokenUsage, format_token_count


def _work_root() -> Path:
    env = os.environ.get("OCR_GATEWAY_WORK_ROOT", "").strip()
    if env:
        return Path(env)
    return Path.home() / ".ocr-gateway" / "work"


def review_index_path() -> Path:
    custom = os.environ.get("OCR_REVIEW_INDEX_PATH", "").strip()
    if custom:
        return Path(custom)
    return _work_root() / "review-index.jsonl"


def gitlab_public_url() -> str:
    return os.environ.get("OCR_GATEWAY_GITLAB_PUBLIC_URL", "http://localhost:8000").rstrip("/")


def mr_web_url(project_path: str, mr_iid: str) -> str:
    path = project_path.strip("/")
    return f"{gitlab_public_url()}/{path}/-/merge_requests/{mr_iid}"


@dataclass
class ReviewRecord:
    job_id: str
    project_id: str
    project_path: str
    mr_iid: str
    target_branch: str = ""
    commit_sha: str = ""
    status: str = "success"  # success | failed | running
    message: str = ""
    finished_at: float = field(default_factory=time.time)
    session_id: str = ""
    encoded_repo: str = ""
    comment_count: int = 0
    severity: dict[str, int] = field(default_factory=lambda: {"HIGH": 0, "MEDIUM": 0, "LOW": 0})
    tokens: dict[str, int] = field(
        default_factory=lambda: {
            "prompt": 0,
            "completion": 0,
            "total": 0,
            "llm_requests": 0,
        }
    )
    high_preview: list[dict[str, Any]] = field(default_factory=list)

    @property
    def mr_key(self) -> tuple[str, str]:
        return self.project_id, self.mr_iid

    @property
    def has_high(self) -> bool:
        return int(self.severity.get("HIGH", 0)) > 0

    @property
    def gitlab_mr_url(self) -> str:
        return mr_web_url(self.project_path, self.mr_iid)

    def session_dashboard_url(self) -> str:
        if self.encoded_repo and self.session_id:
            from urllib.parse import quote

            return f"/r/{quote(self.encoded_repo, safe='')}/{quote(self.session_id, safe='')}"
        return ""

    def official_viewer_url(self) -> str:
        from session_telemetry import official_viewer_url

        base = official_viewer_url()
        if self.encoded_repo and self.session_id:
            return f"{base}/r/{self.encoded_repo}/{self.session_id}"
        return base

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReviewRecord:
        known = {f.name for f in cls.__dataclass_fields__.values()}  # type: ignore[attr-defined]
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _severity_from_counts(severity: SeverityCounts) -> dict[str, int]:
    return severity.to_dict()


def _tokens_from_usage(tokens: TokenUsage) -> dict[str, int]:
    return {
        "prompt": tokens.prompt_tokens,
        "completion": tokens.completion_tokens,
        "total": tokens.total,
        "llm_requests": tokens.request_count,
    }


def _high_preview_from_session(session) -> list[dict[str, Any]]:
    preview = []
    for comment in session.high_comments[:3]:
        preview.append(
            {
                "file_path": comment.file_path,
                "line": comment.line,
                "snippet": comment.snippet,
            }
        )
    return preview


def append_review_record(record: ReviewRecord, path: Path | None = None) -> None:
    index_path = path or review_index_path()
    index_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record.to_dict(), ensure_ascii=False)
    with index_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def load_all_records(path: Path | None = None) -> list[ReviewRecord]:
    index_path = path or review_index_path()
    if not index_path.is_file():
        return []

    records: list[ReviewRecord] = []
    with index_path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(ReviewRecord.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                continue
    return records


def list_sessions_for_mr(
    project_id: str,
    mr_iid: str,
    path: Path | None = None,
) -> list[ReviewRecord]:
    records = [
        r
        for r in load_all_records(path)
        if r.project_id == project_id and r.mr_iid == mr_iid
    ]
    records.sort(key=lambda r: r.finished_at, reverse=True)
    return records


def list_mr_latest_reviews(path: Path | None = None) -> list[ReviewRecord]:
    """One row per (project_id, mr_iid) — latest finished_at."""
    by_key: dict[tuple[str, str], ReviewRecord] = {}
    for record in load_all_records(path):
        key = record.mr_key
        existing = by_key.get(key)
        if existing is None or record.finished_at >= existing.finished_at:
            by_key[key] = record
    results = list(by_key.values())
    results.sort(key=lambda r: r.finished_at, reverse=True)
    return results


def build_record_from_session(
    *,
    job_id: str,
    req,
    status: str,
    message: str = "",
    comment_count: int = 0,
    session=None,
) -> ReviewRecord:
    severity = SeverityCounts()
    tokens = TokenUsage()
    high_preview: list[dict[str, Any]] = []
    session_id = ""
    encoded_repo = ""

    if session is not None:
        severity = session.severity
        tokens = session.tokens
        high_preview = _high_preview_from_session(session)
        session_id = session.session_id
        encoded_repo = session.repo_slug

    return ReviewRecord(
        job_id=job_id,
        project_id=req.project_id,
        project_path=req.project_path,
        mr_iid=req.mr_iid,
        target_branch=req.target_branch,
        commit_sha=req.commit_sha,
        status=status,
        message=message,
        finished_at=time.time(),
        session_id=session_id,
        encoded_repo=encoded_repo,
        comment_count=comment_count,
        severity=_severity_from_counts(severity),
        tokens=_tokens_from_usage(tokens),
        high_preview=high_preview,
    )


def finished_at_datetime(record: ReviewRecord) -> datetime:
    return datetime.fromtimestamp(record.finished_at, tz=timezone.utc)


def compute_kpis(records: list[ReviewRecord], queue_depth: int = 0) -> dict[str, Any]:
    now = datetime.now(tz=timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    latest = list_mr_latest_reviews()
    today_count = sum(1 for r in records if r.finished_at >= today_start and r.status == "success")
    open_high = sum(int(r.severity.get("HIGH", 0)) for r in latest if r.status == "success")
    week_tokens = [
        int(r.tokens.get("total", 0))
        for r in records
        if r.finished_at >= now.timestamp() - 7 * 86400 and r.status == "success"
    ]
    week_tokens.sort()
    median_tokens = week_tokens[len(week_tokens) // 2] if week_tokens else 0
    return {
        "today_reviews": today_count,
        "open_high": open_high,
        "queue_depth": queue_depth,
        "median_tokens_7d": median_tokens,
        "median_tokens_7d_fmt": format_token_count(median_tokens),
    }

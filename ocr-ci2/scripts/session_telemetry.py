"""Scan OCR session JSONL for severity telemetry (~/.opencodereview/sessions).

Used by the Severity Dashboard (:5484). Rules align with E2E lib/ocr_session.py:
only ``type=tool_call`` + ``tool_name=code_comment`` arguments are counted.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SEVERITY_RE = re.compile(r"\[(HIGH|MEDIUM|LOW)\]")
SEVERITY_LEVELS = ("HIGH", "MEDIUM", "LOW")


def sessions_root() -> Path:
    env = os.environ.get("OCR_SESSIONS_DIR", "").strip()
    if env:
        return Path(env)
    return Path.home() / ".opencodereview" / "sessions"


def official_viewer_url() -> str:
    return os.environ.get("OCR_VIEWER_URL", "http://localhost:5483").rstrip("/")


@dataclass
class SeverityCounts:
    high: int = 0
    medium: int = 0
    low: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, int] | None) -> SeverityCounts:
        data = data or {}
        return cls(
            high=int(data.get("HIGH", 0)),
            medium=int(data.get("MEDIUM", 0)),
            low=int(data.get("LOW", 0)),
        )

    def to_dict(self) -> dict[str, int]:
        return {"HIGH": self.high, "MEDIUM": self.medium, "LOW": self.low}

    def total(self) -> int:
        return self.high + self.medium + self.low

    def add(self, other: SeverityCounts) -> None:
        self.high += other.high
        self.medium += other.medium
        self.low += other.low

    def add_counts(self, counts: dict[str, int]) -> None:
        self.high += int(counts.get("HIGH", 0))
        self.medium += int(counts.get("MEDIUM", 0))
        self.low += int(counts.get("LOW", 0))


@dataclass
class SeverityComment:
    file_path: str
    line: int
    snippet: str
    level: str


@dataclass
class SessionTelemetry:
    session_id: str
    repo_slug: str
    cwd: str = ""
    git_branch: str = ""
    timestamp: datetime | None = None
    last_modified: datetime | None = None
    jsonl_path: str = ""
    severity: SeverityCounts = field(default_factory=SeverityCounts)
    high_comments: list[SeverityComment] = field(default_factory=list)

    @property
    def has_high(self) -> bool:
        return self.severity.high > 0

    def official_viewer_url(self) -> str:
        base = official_viewer_url()
        if self.session_id and self.repo_slug:
            return f"{base}/r/{self.repo_slug}/{self.session_id}"
        return base


@dataclass
class RepoTelemetry:
    encoded_path: str
    display_name: str
    session_count: int
    last_modified: datetime | None
    severity: SeverityCounts = field(default_factory=SeverityCounts)

    @property
    def has_high(self) -> bool:
        return self.severity.high > 0


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _comment_text_from_tool_call(obj: dict[str, Any]) -> str:
    if obj.get("type") != "tool_call" or obj.get("tool_name") != "code_comment":
        return ""
    args = obj.get("arguments")
    if isinstance(args, dict):
        return str(args.get("content") or args.get("comment") or "")
    if isinstance(args, str):
        parsed = _parse_tool_arguments(args)
        if parsed:
            return str(parsed.get("content") or parsed.get("comment") or args)
        return args
    return ""


def count_severities_in_text(text: str) -> dict[str, int]:
    counts = {level: 0 for level in SEVERITY_LEVELS}
    for match in SEVERITY_RE.finditer(text or ""):
        counts[match.group(1)] += 1
    return counts


def _first_severity_level(text: str) -> str | None:
    match = SEVERITY_RE.search(text or "")
    return match.group(1) if match else None


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_safe_path_segment(name: str) -> bool:
    if not name or name in (".", ".."):
        return False
    if ".." in name or "/" in name or "\\" in name:
        return False
    return True


def _safe_repo_dir(root: Path, encoded_repo: str) -> Path | None:
    if not _is_safe_path_segment(encoded_repo):
        return None
    repo_dir = (root / encoded_repo).resolve()
    try:
        repo_dir.relative_to(root.resolve())
    except ValueError:
        return None
    return repo_dir if repo_dir.is_dir() else None


def _safe_session_file(root: Path, encoded_repo: str, session_id: str) -> Path | None:
    if not _is_safe_path_segment(session_id):
        return None
    repo_dir = _safe_repo_dir(root, encoded_repo)
    if repo_dir is None:
        return None
    path = (repo_dir / f"{session_id}.jsonl").resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def _mtime_as_datetime(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None


def scan_session_jsonl(path: Path) -> SessionTelemetry:
    """Parse one JSONL file and return severity telemetry."""
    repo_slug = path.parent.name
    session_id = path.stem
    cwd = ""
    git_branch = ""
    timestamp: datetime | None = None
    severity = SeverityCounts()
    high_comments: list[SeverityComment] = []

    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue

            evt_type = obj.get("type")
            if evt_type == "session_start":
                session_id = str(obj.get("sessionId") or session_id)
                cwd = str(obj.get("cwd") or cwd)
                git_branch = str(obj.get("gitBranch") or git_branch)
                timestamp = _parse_timestamp(obj.get("timestamp")) or timestamp
                continue

            if evt_type != "tool_call" or obj.get("tool_name") != "code_comment":
                continue

            text = _comment_text_from_tool_call(obj)
            if not text:
                continue

            level_counts = count_severities_in_text(text)
            severity.add_counts(level_counts)

            level = _first_severity_level(text)
            if level == "HIGH":
                args = obj.get("arguments")
                parsed = _parse_tool_arguments(args if not isinstance(args, dict) else args)
                file_path = str(
                    obj.get("filePath")
                    or obj.get("file_path")
                    or parsed.get("path")
                    or parsed.get("file_path")
                    or ""
                )
                line_no = 0
                for key in ("line", "end_line", "start_line"):
                    if parsed.get(key):
                        try:
                            line_no = int(parsed[key])
                            break
                        except (TypeError, ValueError):
                            pass
                snippet = text.strip()
                if len(snippet) > 240:
                    snippet = snippet[:237] + "..."
                high_comments.append(
                    SeverityComment(
                        file_path=file_path,
                        line=line_no,
                        snippet=snippet,
                        level=level,
                    )
                )

    return SessionTelemetry(
        session_id=session_id,
        repo_slug=repo_slug,
        cwd=cwd,
        git_branch=git_branch,
        timestamp=timestamp,
        last_modified=_mtime_as_datetime(path),
        jsonl_path=str(path),
        severity=severity,
        high_comments=high_comments,
    )


def list_repo_sessions(root: Path, encoded_repo: str) -> list[SessionTelemetry]:
    repo_dir = _safe_repo_dir(root, encoded_repo)
    if repo_dir is None:
        return []

    sessions: list[SessionTelemetry] = []
    for entry in sorted(repo_dir.glob("*.jsonl")):
        if not _is_safe_path_segment(entry.stem):
            continue
        try:
            sessions.append(scan_session_jsonl(entry))
        except OSError:
            continue

    sessions.sort(
        key=lambda s: s.last_modified or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return sessions


def discover_repos(root: Path | None = None) -> list[RepoTelemetry]:
    root = root or sessions_root()
    if not root.is_dir():
        return []

    repos: list[RepoTelemetry] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue

        sessions = list_repo_sessions(root, entry.name)
        if not sessions:
            continue

        severity = SeverityCounts()
        last_modified: datetime | None = None
        display_name = entry.name
        for session in sessions:
            severity.add(session.severity)
            if session.last_modified and (
                last_modified is None or session.last_modified > last_modified
            ):
                last_modified = session.last_modified
        # sessions sorted by mtime desc — use newest cwd for display name
        for session in sessions:
            if session.cwd:
                display_name = Path(session.cwd).name or display_name
                break

        repos.append(
            RepoTelemetry(
                encoded_path=entry.name,
                display_name=display_name,
                session_count=len(sessions),
                last_modified=last_modified,
                severity=severity,
            )
        )

    repos.sort(
        key=lambda r: r.last_modified or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )
    return repos


def load_session(root: Path, encoded_repo: str, session_id: str) -> SessionTelemetry | None:
    path = _safe_session_file(root, encoded_repo, session_id)
    if path is None:
        return None
    return scan_session_jsonl(path)

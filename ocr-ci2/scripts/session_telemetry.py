"""Scan OCR session JSONL for severity and token telemetry (~/.opencodereview/sessions).

Used by the OCR Gateway Dashboard (:8010) and ``session_token_report.py``.
Severity rules align with E2E lib/ocr_session.py: only ``type=tool_call`` +
``tool_name=code_comment`` arguments are counted.

Token totals match official OCR viewer (``store.go``): sum ``usage`` on
``type=llm_response`` events.
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
    """官方 OCR viewer 基址。

    默认关闭（返回空字符串），需设置 ``OCR_VIEWER_ENABLED=1`` 才启用。
    启用后读取 ``OCR_VIEWER_URL``（默认 ``http://localhost:5483``）。
    返回空字符串时，Dashboard 不渲染官方 viewer 跳转链接。
    """
    if os.environ.get("OCR_VIEWER_ENABLED", "").strip().lower() not in ("1", "true", "yes"):
        return ""
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
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cache_read_tokens: int = 0
    request_count: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def add(self, other: TokenUsage) -> None:
        self.prompt_tokens += other.prompt_tokens
        self.completion_tokens += other.completion_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.request_count += other.request_count

    def add_usage_dict(self, usage: dict[str, Any] | None) -> None:
        if not usage:
            return
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        self.cache_read_tokens += int(usage.get("cache_read_tokens") or 0)
        self.request_count += 1


def format_token_count(value: int) -> str:
    """Human-readable token count (e.g. 118432 -> 118K)."""
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M"
    if value >= 10_000:
        return f"{round(value / 1000)}K"
    if value >= 1000:
        return f"{value / 1000:.1f}K"
    return str(value)


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
    all_comments: list[SeverityComment] = field(default_factory=list)
    tokens: TokenUsage = field(default_factory=TokenUsage)
    files_reviewed: int | None = None
    duration_seconds: float | None = None
    llm_failures: int = 0
    tool_counts: dict[str, int] = field(default_factory=dict)

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
    tokens: TokenUsage = field(default_factory=TokenUsage)
    latest_tokens: TokenUsage = field(default_factory=TokenUsage)
    latest_severity: SeverityCounts = field(default_factory=SeverityCounts)
    # 与 list_repo_sessions 按 mtime 降序后首条一致，供 Dashboard 内联加载避免二次扫描
    latest_session_id: str = ""

    @property
    def has_high(self) -> bool:
        return self.severity.high > 0

    @property
    def latest_has_high(self) -> bool:
        return self.latest_severity.high > 0


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


def _tool_call_arguments_dict(obj: dict[str, Any]) -> dict[str, Any]:
    args = obj.get("arguments")
    if isinstance(args, dict):
        return args
    if isinstance(args, str):
        return _parse_tool_arguments(args)
    return {}


def _parse_comments_field(raw: Any) -> list[dict[str, Any]]:
    """Parse OCR ``comments`` payload (list, JSON string, or single dict)."""
    if raw is None:
        return []
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return []
        raw = parsed
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [entry for entry in raw if isinstance(entry, dict)]
    return []


def _line_from_mapping(data: dict[str, Any]) -> int:
    for key in ("line", "end_line", "start_line"):
        if data.get(key) is not None:
            try:
                return int(data[key])
            except (TypeError, ValueError):
                continue
    return 0


def _path_from_mapping(data: dict[str, Any]) -> str:
    return str(
        data.get("path")
        or data.get("file_path")
        or data.get("filePath")
        or data.get("filepath")
        or ""
    )


def _text_from_mapping(data: dict[str, Any]) -> str:
    return str(
        data.get("content")
        or data.get("comment")
        or data.get("body")
        or data.get("message")
        or ""
    ).strip()


def iter_code_comment_entries(obj: dict[str, Any]) -> list[tuple[str, str, int]]:
    """Expand one ``code_comment`` tool_call into (text, file_path, line) rows."""
    if obj.get("type") != "tool_call" or obj.get("tool_name") != "code_comment":
        return []

    parsed = _tool_call_arguments_dict(obj)
    entries: list[tuple[str, str, int]] = []

    parent_path = str(
        obj.get("filePath") or obj.get("file_path") or _path_from_mapping(parsed)
    )

    if "comments" in parsed:
        for item in _parse_comments_field(parsed.get("comments")):
            text = _text_from_mapping(item)
            if not text:
                continue
            file_path = _path_from_mapping(item) or parent_path
            entries.append(
                (
                    text,
                    file_path,
                    _line_from_mapping(item),
                )
            )
        if entries:
            return entries

    text = _text_from_mapping(parsed)
    if not text and isinstance(obj.get("arguments"), str):
        raw = str(obj.get("arguments") or "").strip()
        if raw and not parsed:
            text = raw
    if not text:
        return []

    file_path = parent_path or _path_from_mapping(parsed)
    return [(text, file_path, _line_from_mapping(parsed))]


def _comment_text_from_tool_call(obj: dict[str, Any]) -> str:
    parts = [text for text, _, _ in iter_code_comment_entries(obj) if text]
    return "\n".join(parts)


def _severity_comment_from_parts(text: str, file_path: str, line_no: int) -> SeverityComment | None:
    if not text.strip():
        return None
    level = _first_severity_level(text) or "LOW"
    snippet = text.strip()
    if len(snippet) > 240:
        snippet = snippet[:237] + "..."
    return SeverityComment(
        file_path=file_path,
        line=line_no,
        snippet=snippet,
        level=level,
    )


def _extract_comment_from_tool_call(obj: dict[str, Any]) -> SeverityComment | None:
    for text, file_path, line_no in iter_code_comment_entries(obj):
        comment = _severity_comment_from_parts(text, file_path, line_no)
        if comment:
            return comment
    return None


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
    """Parse one JSONL file and return severity + token telemetry."""
    repo_slug = path.parent.name
    session_id = path.stem
    cwd = ""
    git_branch = ""
    timestamp: datetime | None = None
    severity = SeverityCounts()
    high_comments: list[SeverityComment] = []
    all_comments: list[SeverityComment] = []
    tokens = TokenUsage()
    files_reviewed: int | None = None
    duration_seconds: float | None = None
    llm_failures = 0
    tool_counts: dict[str, int] = {}

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

            if evt_type == "session_end":
                if obj.get("files_reviewed") is not None:
                    try:
                        files_reviewed = int(obj["files_reviewed"])
                    except (TypeError, ValueError):
                        pass
                if obj.get("duration_seconds") is not None:
                    try:
                        duration_seconds = float(obj["duration_seconds"])
                    except (TypeError, ValueError):
                        pass
                if obj.get("llm_failures") is not None:
                    try:
                        llm_failures = int(obj["llm_failures"])
                    except (TypeError, ValueError):
                        pass
                continue

            if evt_type == "llm_response":
                usage = obj.get("usage")
                if isinstance(usage, dict):
                    tokens.add_usage_dict(usage)
                continue

            if evt_type != "tool_call":
                continue

            tool_name = str(obj.get("tool_name") or "")
            if tool_name:
                tool_counts[tool_name] = tool_counts.get(tool_name, 0) + 1

            if tool_name != "code_comment":
                continue

            for text, file_path, line_no in iter_code_comment_entries(obj):
                level_counts = count_severities_in_text(text)
                severity.add_counts(level_counts)
                comment = _severity_comment_from_parts(text, file_path, line_no)
                if not comment:
                    continue
                all_comments.append(comment)
                if comment.level == "HIGH":
                    high_comments.append(comment)

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
        all_comments=all_comments,
        tokens=tokens,
        files_reviewed=files_reviewed,
        duration_seconds=duration_seconds,
        llm_failures=llm_failures,
        tool_counts=tool_counts,
    )


def iter_all_sessions(root: Path | None = None) -> list[SessionTelemetry]:
    """Scan every session JSONL under *root* (default: sessions_root())."""
    root = root or sessions_root()
    if not root.is_dir():
        return []

    sessions: list[SessionTelemetry] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        if _safe_repo_dir(root, entry.name) is None:
            continue
        for jsonl in sorted(entry.glob("*.jsonl")):
            if not _is_safe_path_segment(jsonl.stem):
                continue
            try:
                sessions.append(scan_session_jsonl(jsonl))
            except OSError:
                continue
    return sessions


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
        repo_tokens = TokenUsage()
        for session in sessions:
            severity.add(session.severity)
            repo_tokens.add(session.tokens)
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
                tokens=repo_tokens,
                latest_tokens=sessions[0].tokens if sessions else TokenUsage(),
                latest_severity=sessions[0].severity if sessions else SeverityCounts(),
                latest_session_id=sessions[0].session_id if sessions else "",
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


def comment_to_dict(comment: SeverityComment) -> dict[str, Any]:
    """将单条 severity 评论序列化为 dict，供 JSON API / 模板使用。"""
    return {
        "level": comment.level,
        "file_path": comment.file_path,
        "line": comment.line,
        "snippet": comment.snippet,
    }


def group_comments_by_file(comments: list[SeverityComment]) -> list[dict[str, Any]]:
    """按文件聚合评论，供工作台/Session 文件树使用（同文件内 HIGH 优先）。

    返回结构::

        [
          {
            "file_path": str,
            "comment_count": int,
            "severity": {"HIGH": n, "MEDIUM": n, "LOW": n},
            "comments": [{level, file_path, line, snippet}, ...],
          },
          ...
        ]

    文件排序：含 HIGH 的文件优先，其次 MEDIUM，最后 LOW；同级按 HIGH 数量降序、路径升序。
    空文件路径归入 "(unknown)"。
    """
    level_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    by_file: dict[str, list[SeverityComment]] = {}
    for comment in comments:
        key = comment.file_path.strip() if comment.file_path else "(unknown)"
        by_file.setdefault(key, []).append(comment)

    files: list[dict[str, Any]] = []
    for path, items in by_file.items():
        items_sorted = sorted(
            items,
            key=lambda c: (level_order.get(c.level, 9), c.line, c.snippet),
        )
        sev = SeverityCounts()
        for comment in items_sorted:
            if comment.level == "HIGH":
                sev.high += 1
            elif comment.level == "MEDIUM":
                sev.medium += 1
            else:
                sev.low += 1
        files.append(
            {
                "file_path": path,
                "comment_count": len(items_sorted),
                "severity": sev.to_dict(),
                "comments": [comment_to_dict(c) for c in items_sorted],
            }
        )

    def _file_sort_key(entry: dict[str, Any]) -> tuple:
        sev = entry["severity"]
        # 含 HIGH 的文件排最前，其次 MEDIUM，最后 LOW
        tier = 0 if sev.get("HIGH") else (1 if sev.get("MEDIUM") else 2)
        return (tier, -int(sev.get("HIGH", 0)), -int(sev.get("MEDIUM", 0)), entry["file_path"])

    files.sort(key=_file_sort_key)
    return files

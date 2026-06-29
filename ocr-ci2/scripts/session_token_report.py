#!/usr/bin/env python3
"""Scan OCR session JSONL and report token usage rankings.

Usage::

    python scripts/session_token_report.py
    python scripts/session_token_report.py --top 10 --format csv

Token totals match official OCR viewer (``store.go``): sum ``usage`` on
``type=llm_response`` events.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

from session_telemetry import (  # noqa: E402
    SessionTelemetry,
    format_token_count,
    iter_all_sessions,
    sessions_root,
)


def _repo_display(session: SessionTelemetry) -> str:
    if session.cwd:
        return Path(session.cwd).name
    return session.repo_slug


def _sorted_sessions(sessions: list[SessionTelemetry]) -> list[SessionTelemetry]:
    return sorted(
        sessions,
        key=lambda s: (s.tokens.total, s.tokens.request_count),
        reverse=True,
    )


def render_markdown(sessions: list[SessionTelemetry], *, top: int | None) -> str:
    rows = _sorted_sessions(sessions)
    if top is not None:
        rows = rows[:top]

    lines = [
        "# OCR Session Token Report",
        "",
        f"- Sessions root: `{sessions_root()}`",
        f"- Total sessions: **{len(sessions)}**",
        "",
        "| Rank | Repo | Session | Total | Prompt | Completion | LLM # | Files | Branch |",
        "|------|------|---------|-------|--------|------------|-------|-------|--------|",
    ]
    for idx, session in enumerate(rows, start=1):
        t = session.tokens
        files = session.files_reviewed if session.files_reviewed is not None else "—"
        branch = session.git_branch or "—"
        lines.append(
            f"| {idx} | {_repo_display(session)} | `{session.session_id[:8]}…` "
            f"| {format_token_count(t.total)} ({t.total:,}) "
            f"| {t.prompt_tokens:,} | {t.completion_tokens:,} "
            f"| {t.request_count} | {files} | {branch} |"
        )
    if not rows:
        lines.append("| — | — | — | — | — | — | — | — | — |")
    return "\n".join(lines) + "\n"


def render_csv(sessions: list[SessionTelemetry], *, top: int | None) -> str:
    import io

    rows = _sorted_sessions(sessions)
    if top is not None:
        rows = rows[:top]

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "rank",
            "repo",
            "session_id",
            "total_tokens",
            "prompt_tokens",
            "completion_tokens",
            "cache_read_tokens",
            "llm_requests",
            "files_reviewed",
            "duration_seconds",
            "llm_failures",
            "git_branch",
            "jsonl_path",
        ]
    )
    for idx, session in enumerate(rows, start=1):
        t = session.tokens
        writer.writerow(
            [
                idx,
                _repo_display(session),
                session.session_id,
                t.total,
                t.prompt_tokens,
                t.completion_tokens,
                t.cache_read_tokens,
                t.request_count,
                session.files_reviewed if session.files_reviewed is not None else "",
                session.duration_seconds if session.duration_seconds is not None else "",
                session.llm_failures,
                session.git_branch,
                session.jsonl_path,
            ]
        )
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OCR session token usage report")
    parser.add_argument(
        "--top",
        type=int,
        default=None,
        help="Only show top N sessions by total tokens",
    )
    parser.add_argument(
        "--format",
        choices=("markdown", "csv"),
        default="markdown",
        help="Output format (default: markdown)",
    )
    args = parser.parse_args(argv)

    sessions = iter_all_sessions()
    if args.format == "csv":
        print(render_csv(sessions, top=args.top), end="")
    else:
        print(render_markdown(sessions, top=args.top), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

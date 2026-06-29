"""Compare token usage for recent OCR Gateway sessions."""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "scripts"))

from session_telemetry import iter_all_sessions  # noqa: E402


def _session_label(session) -> str:
    """Best-effort repo label from cwd or encoded repo slug."""
    if session.cwd:
        return Path(session.cwd).name
    return session.repo_slug


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List recent OCR sessions sorted by mtime (Gateway worktrees included)"
    )
    parser.add_argument(
        "--top",
        type=int,
        default=12,
        help="Number of sessions to show (default: 12)",
    )
    args = parser.parse_args(argv)

    sessions = iter_all_sessions()
    sessions.sort(
        key=lambda s: s.last_modified or datetime.min.replace(tzinfo=timezone.utc),
        reverse=True,
    )

    print(f"recent sessions: {len(sessions)}")
    print(
        f"{'session':10} {'repo':20} {'total':>12} {'llm':>5} "
        f"{'read':>5} {'find':>5} {'cache':>6}"
    )
    for session in sessions[: max(args.top, 0)]:
        t = session.tokens
        fr = session.tool_counts.get("file_read", 0)
        ff = session.tool_counts.get("file_find", 0)
        print(
            f"{session.session_id[:8]:10} {_session_label(session)[:20]:20} "
            f"{t.total:12,} {t.request_count:5} {fr:5} {ff:5} {t.cache_read_tokens:6}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

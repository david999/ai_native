#!/usr/bin/env python3
"""Compare OCR token usage with vs without ``.opencodereview/rule.json``.

Runs ``ocr review`` twice on the same repo/refs (with rule.json, then without),
waits for session JSONL, and prints a comparison table.

Usage::

    cd ocr-ci2
    python scripts/token_compare_rule_json.py \\
        --repo ../test_data/datacalc-web \\
        --branch ocr-test/D05_rule_severity_prefix \\
        --from origin/master --to HEAD

Requires: ``ocr`` on PATH, valid ``~/.opencodereview/config.json``, LLM available.
Set ``OCR_TEST_LIVE=1`` for pytest live wrapper.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_ROOT / "scripts"))

from session_telemetry import SessionTelemetry, scan_session_jsonl, sessions_root  # noqa: E402

DEFAULT_REPO = _ROOT.parent / "test_data" / "datacalc-web"
RULE_REL = Path(".opencodereview") / "rule.json"
SESSION_WAIT_SEC = 90
SESSION_POLL_SEC = 2


@dataclass
class ReviewArm:
    label: str
    had_rule_json: bool
    session: SessionTelemetry | None = None
    error: str = ""


def _resolve_ocr() -> str:
    exe = shutil.which("ocr")
    if not exe:
        raise FileNotFoundError("ocr CLI not found in PATH")
    return exe


def _git_run(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _known_jsonl_paths(root: Path) -> set[Path]:
    if not root.is_dir():
        return set()
    return {p.resolve() for p in root.rglob("*.jsonl")}


def _wait_new_session(
    repo: Path,
    *,
    before: set[Path],
    started_at: float,
) -> SessionTelemetry | None:
    root = sessions_root()
    deadline = time.monotonic() + SESSION_WAIT_SEC
    repo_resolved = repo.resolve()

    while time.monotonic() < deadline:
        if root.is_dir():
            candidates: list[Path] = []
            for path in root.rglob("*.jsonl"):
                try:
                    resolved = path.resolve()
                except OSError:
                    continue
                if resolved in before:
                    continue
                if path.stat().st_mtime < started_at - 5:
                    continue
                candidates.append(path)

            for path in sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True):
                try:
                    session = scan_session_jsonl(path)
                except OSError:
                    continue
                if not session.cwd:
                    continue
                try:
                    if Path(session.cwd).resolve() == repo_resolved:
                        return session
                except OSError:
                    continue
        time.sleep(SESSION_POLL_SEC)
    return None


def _build_review_argv(
    ocr_exe: str,
    repo: Path,
    *,
    from_ref: str,
    to_ref: str,
    max_tools: int | None,
    exclude: str | None,
) -> list[str]:
    argv = [
        ocr_exe,
        "review",
        "--repo",
        str(repo),
        "--from",
        from_ref,
        "--to",
        to_ref,
        "--format",
        "json",
        "--audience",
        "agent",
        "--concurrency",
        "1",
    ]
    if max_tools is not None and max_tools > 0:
        argv.extend(["--max-tools", str(max_tools)])
    if exclude:
        argv.extend(["--exclude", exclude])
    return argv


def _run_ocr_review(
    repo: Path,
    *,
    from_ref: str,
    to_ref: str,
    max_tools: int | None,
    exclude: str | None,
    before_jsonl: set[Path],
) -> tuple[SessionTelemetry | None, str]:
    ocr_exe = _resolve_ocr()
    argv = _build_review_argv(
        ocr_exe,
        repo,
        from_ref=from_ref,
        to_ref=to_ref,
        max_tools=max_tools,
        exclude=exclude,
    )
    started_at = time.time()
    try:
        proc = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
        )
    except subprocess.TimeoutExpired:
        return None, "ocr review timed out after 3600s"

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "")[-800:]
        return None, f"ocr review exit {proc.returncode}: {tail}"

    session = _wait_new_session(repo, before=before_jsonl, started_at=started_at)
    if session is None:
        return None, "session JSONL not found after review"
    return session, ""


def _rule_json_backup(repo: Path) -> tuple[Path, bytes | None]:
    """Return (rule_path, backup_bytes). backup None if file did not exist."""
    path = repo / RULE_REL
    if not path.is_file():
        return path, None
    return path, path.read_bytes()


def _restore_rule_json(path: Path, backup: bytes | None) -> None:
    if backup is None:
        if path.is_file():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(backup)


def run_comparison(
    repo: Path,
    *,
    from_ref: str,
    to_ref: str,
    branch: str | None = None,
    max_tools: int | None = None,
    exclude: str | None = None,
    skip_with: bool = False,
) -> tuple[ReviewArm, ReviewArm]:
    repo = repo.resolve()
    if branch:
        _git_run(repo, "fetch", "origin")
        _git_run(repo, "checkout", branch)

    rule_path, rule_backup = _rule_json_backup(repo)
    arms: list[ReviewArm] = []

    # --- with rule.json ---
    if skip_with:
        arms.append(ReviewArm(label="有 rule.json", had_rule_json=True))
    else:
        if rule_backup is not None:
            rule_path.write_bytes(rule_backup)
        before = _known_jsonl_paths(sessions_root())
        session, err = _run_ocr_review(
            repo,
            from_ref=from_ref,
            to_ref=to_ref,
            max_tools=max_tools,
            exclude=exclude,
            before_jsonl=before,
        )
        arms.append(
            ReviewArm(
                label="有 rule.json",
                had_rule_json=rule_path.is_file(),
                session=session,
                error=err,
            )
        )

    # --- without rule.json ---
    if rule_path.is_file():
        rule_path.unlink()
    before = _known_jsonl_paths(sessions_root())
    session, err = _run_ocr_review(
        repo,
        from_ref=from_ref,
        to_ref=to_ref,
        max_tools=max_tools,
        exclude=exclude,
        before_jsonl=before,
    )
    arms.append(
        ReviewArm(
            label="无 rule.json",
            had_rule_json=False,
            session=session,
            error=err,
        )
    )

    _restore_rule_json(rule_path, rule_backup)
    return arms[0], arms[1]


def render_markdown(
    with_arm: ReviewArm,
    without_arm: ReviewArm,
    *,
    repo: Path,
    from_ref: str,
    to_ref: str,
) -> str:
    lines = [
        "# rule.json 有无 Token 对比",
        "",
        f"- Repo: `{repo}`",
        f"- Diff: `{from_ref}` → `{to_ref}`",
        "",
        "| 配置 | Session | Total | Prompt | LLM # | file_read | file_find | 备注 |",
        "|------|---------|------:|-------:|------:|----------:|----------:|------|",
    ]

    def _row(arm: ReviewArm) -> str:
        if arm.error:
            return f"| {arm.label} | — | — | — | — | — | — | {arm.error[:60]} |"
        s = arm.session
        assert s is not None
        t = s.tokens
        fr = s.tool_counts.get("file_read", 0)
        ff = s.tool_counts.get("file_find", 0)
        return (
            f"| {arm.label} | `{s.session_id[:8]}…` | {t.total:,} | {t.prompt_tokens:,} "
            f"| {t.request_count} | {fr} | {ff} | — |"
        )

    lines.append(_row(with_arm))
    lines.append(_row(without_arm))

    if with_arm.session and without_arm.session and not with_arm.error and not without_arm.error:
        wt = with_arm.session.tokens.total
        wot = without_arm.session.tokens.total
        delta = wot - wt
        pct = (delta / wt * 100) if wt else 0
        lines.extend(
            [
                "",
                f"**无 rule.json vs 有 rule.json**：total {delta:+,} ({pct:+.1f}%)",
            ]
        )

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare OCR tokens with/without rule.json")
    parser.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    parser.add_argument("--branch", default="ocr-test/D05_rule_severity_prefix")
    parser.add_argument("--from", dest="from_ref", default="origin/master")
    parser.add_argument("--to", dest="to_ref", default="HEAD")
    parser.add_argument("--max-tools", type=int, default=int(os.environ.get("OCR_REVIEW_MAX_TOOLS", "0") or 0))
    parser.add_argument("--exclude", default=os.environ.get("OCR_REVIEW_EXCLUDE", ""))
    parser.add_argument("--skip-with", action="store_true", help="Skip 'with rule' run (use prior session only)")
    parser.add_argument("-o", "--output", type=Path, help="Write markdown report to file")
    args = parser.parse_args(argv)

    max_tools = args.max_tools if args.max_tools > 0 else None
    exclude = args.exclude.strip() or None

    with_arm, without_arm = run_comparison(
        args.repo,
        from_ref=args.from_ref,
        to_ref=args.to_ref,
        branch=args.branch,
        max_tools=max_tools,
        exclude=exclude,
        skip_with=args.skip_with,
    )

    md = render_markdown(
        with_arm,
        without_arm,
        repo=args.repo.resolve(),
        from_ref=args.from_ref,
        to_ref=args.to_ref,
    )
    print(md, end="")

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(md, encoding="utf-8")

    if with_arm.error or without_arm.error:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

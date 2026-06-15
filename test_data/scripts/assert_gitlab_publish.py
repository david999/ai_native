#!/usr/bin/env python3
"""断言 GitLab MR 上存在 AICR 发布的摘要 note（REVIEW_DRY_RUN=0）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

AICR_MARKERS = (
    "**aicr**",
    "## aicr",
    "aicr review",
    "review score",
    "code review",
    "评审",
)


def load_dotenv() -> None:
    aicr = REPO_ROOT / "aicr-reviewer"
    if str(aicr) not in sys.path:
        sys.path.insert(0, str(aicr))
    from app.env_loader import apply_monorepo_env

    apply_monorepo_env()


def api_get(url: str, token: str) -> list | dict:
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def note_looks_like_aicr(body: str, expected_score: float | None = None) -> bool:
    text = (body or "").lower()
    if expected_score is not None:
        score_str = f"{expected_score:g}"
        if f"score: {score_str}" in text or f"score {score_str}" in text:
            return True
        if score_str in text and ("aicr" in text or "review" in text):
            return True
    return any(m in text for m in AICR_MARKERS)


def find_aicr_notes(notes: list, expected_score: float | None) -> list[dict]:
    hits = []
    for note in notes:
        body = note.get("body") or ""
        if note_looks_like_aicr(body, expected_score):
            hits.append(note)
    return hits


def assert_mr_published(
    gitlab_url: str,
    token: str,
    project_id: int,
    mr_iid: int,
    *,
    expected_score: float | None = None,
) -> dict:
    base = f"{gitlab_url.rstrip('/')}/api/v4/projects/{project_id}/merge_requests/{mr_iid}"
    notes = api_get(f"{base}/notes?sort=desc&order_by=updated_at&per_page=100", token)
    if not isinstance(notes, list):
        notes = []

    discussions: list = []
    try:
        discussions = api_get(f"{base}/discussions?per_page=100", token)
        if not isinstance(discussions, list):
            discussions = []
    except urllib.error.HTTPError:
        discussions = []

    aicr_notes = find_aicr_notes(notes, expected_score)
    inline_count = 0
    for disc in discussions:
        for note in disc.get("notes") or []:
            if note.get("type") == "DiffNote" or note.get("position"):
                inline_count += 1

    ok = len(aicr_notes) > 0
    return {
        "ok": ok,
        "note_count": len(notes),
        "aicr_note_count": len(aicr_notes),
        "inline_discussion_count": inline_count,
        "errors": [] if ok else ["no AICR summary note found on MR"],
        "sample_bodies": [(n.get("body") or "")[:200] for n in aicr_notes[:2]],
    }


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Assert AICR published MR notes")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--mr-iid", type=int, required=True)
    parser.add_argument("--expected-score", type=float, default=None)
    parser.add_argument("--report-json", metavar="PATH")
    parser.add_argument("--dry-run-ok", action="store_true", help="Pass when REVIEW_DRY_RUN=1")
    args = parser.parse_args()

    dry_run = os.environ.get("REVIEW_DRY_RUN", "0") == "1"
    if dry_run and args.dry_run_ok:
        result = {"ok": True, "skipped": True, "reason": "REVIEW_DRY_RUN=1"}
    else:
        gitlab_url = os.environ.get("GITLAB_URL", "http://localhost:8000")
        token = os.environ.get("AICR_BOT_TOKEN") or os.environ.get("ROOT_PAT", "")
        if not token:
            print("FAIL: no AICR_BOT_TOKEN", file=sys.stderr)
            return 1
        result = assert_mr_published(
            gitlab_url,
            token,
            args.project_id,
            args.mr_iid,
            expected_score=args.expected_score,
        )

    if args.report_json:
        Path(args.report_json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    if result.get("ok"):
        print(f"OK GitLab publish check (aicr_notes={result.get('aicr_note_count', 0)})")
        return 0
    for err in result.get("errors") or ["publish check failed"]:
        print(f"FAIL: {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

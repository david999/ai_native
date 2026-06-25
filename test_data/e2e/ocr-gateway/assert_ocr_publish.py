"""Assert OpenCodeReview comments were posted on GitLab MR."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

E2E_ROOT = Path(__file__).resolve().parent
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from lib.gitlab_api import (
    get_mr_discussions,
    get_mr_notes,
    gitlab_token,
    gitlab_url,
    load_dotenv,
)
from lib.scenario_manifest import get_scenario_spec

OCR_MARKERS = (
    "opencodereview",
    "open code review",
    "open-code-review",
)


def parse_gitlab_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def note_is_ocr(body: str) -> bool:
    text = (body or "").lower()
    return any(m in text for m in OCR_MARKERS)


def inline_note_is_review(note: dict) -> bool:
    """Heuristic: Gateway inline / fallback-style review comment (not GitLab system noise)."""
    if note.get("system"):
        return False
    body = note.get("body") or ""
    if note_is_ocr(body):
        return True
    if "```suggestion" in body or "**Suggestion:**" in body:
        return True
    if note.get("type") == "DiffNote" or note.get("position"):
        return bool(body.strip())
    return False


def note_created_after(note: dict, since: datetime | None) -> bool:
    if since is None:
        return True
    ts = parse_gitlab_ts(note.get("created_at"))
    if ts is None:
        return False
    return ts >= since


def collect_ocr_content(
    notes: list,
    discussions: list,
    *,
    since: datetime | None = None,
) -> dict[str, Any]:
    ocr_notes = [
        n for n in notes
        if note_is_ocr(n.get("body") or "") and note_created_after(n, since)
    ]
    inline_bodies: list[str] = []
    inline_count = 0
    for disc in discussions:
        for note in disc.get("notes") or []:
            if not note_created_after(note, since):
                continue
            body = note.get("body") or ""
            is_inline = note.get("type") == "DiffNote" or note.get("position")
            if is_inline and inline_note_is_review(note):
                inline_count += 1
                inline_bodies.append(body)
            elif note_is_ocr(body):
                inline_bodies.append(body)

    all_text = "\n".join(
        [(n.get("body") or "") for n in ocr_notes] + inline_bodies
    ).lower()
    return {
        "ocr_note_count": len(ocr_notes),
        "inline_count": inline_count,
        "all_text": all_text,
        "ocr_notes": ocr_notes,
        "sample_bodies": [(n.get("body") or "")[:240] for n in ocr_notes[:3]],
        "since": since.isoformat() if since else None,
    }


def assert_ocr_publish(
    project_id: int,
    mr_iid: int,
    scenario_id: str,
    *,
    compare_inline_count: int | None = None,
    since: datetime | None = None,
) -> dict[str, Any]:
    token = gitlab_token()
    if not token:
        return {"ok": False, "errors": ["missing GitLab token"]}

    spec = get_scenario_spec(scenario_id)
    notes = get_mr_notes(token, project_id, mr_iid)
    discussions = get_mr_discussions(token, project_id, mr_iid)
    collected = collect_ocr_content(notes, discussions, since=since)

    errors: list[str] = []
    warnings: list[str] = []

    min_notes = int(spec.get("min_ocr_notes", 1))
    if collected["ocr_note_count"] < min_notes:
        scope = f"since {since.isoformat()}" if since else "on MR"
        errors.append(
            f"expected >= {min_notes} OpenCodeReview note(s) {scope}, "
            f"got {collected['ocr_note_count']}"
        )

    min_inline = int(spec.get("min_inline_comments", 0))
    if collected["inline_count"] < min_inline:
        errors.append(
            f"expected >= {min_inline} inline comment(s) this run, "
            f"got {collected['inline_count']}"
        )

    keywords = [str(k).lower() for k in (spec.get("must_find_keywords") or [])]
    missing_kw = [kw for kw in keywords if kw and kw not in collected["all_text"]]
    if missing_kw:
        msg = f"keywords not found in MR OCR content (this run): {missing_kw}"
        if spec.get("keyword_warnings_only"):
            warnings.append(msg)
        else:
            errors.append(msg)

    if spec.get("relax_comment_count") and compare_inline_count is not None:
        if collected["inline_count"] > compare_inline_count + 2:
            warnings.append(
                f"inline count {collected['inline_count']} > compare {compare_inline_count} (relaxed)"
            )
        looks_good = "looks good" in collected["all_text"] or "no comments" in collected["all_text"]
        if not looks_good and collected["inline_count"] >= compare_inline_count:
            warnings.append("D04: issue count not clearly reduced vs D02 (relaxed check)")

    ok = len(errors) == 0
    return {
        "ok": ok,
        "errors": errors,
        "warnings": warnings,
        "scenario_id": scenario_id,
        "ocr_note_count": collected["ocr_note_count"],
        "inline_count": collected["inline_count"],
        "sample_bodies": collected["sample_bodies"],
        "assert_since": collected.get("since"),
        "gitlab_url": gitlab_url(),
        "project_id": project_id,
        "mr_iid": mr_iid,
    }


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Assert OpenCodeReview published on MR")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--mr-iid", type=int, required=True)
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--compare-inline-count", type=int, default=None)
    parser.add_argument("--since-iso", default="", help="Only count notes at or after this UTC time")
    parser.add_argument("--report-json", metavar="PATH")
    args = parser.parse_args()

    since = None
    if args.since_iso:
        since = datetime.fromisoformat(args.since_iso.replace("Z", "+00:00"))

    result = assert_ocr_publish(
        args.project_id,
        args.mr_iid,
        args.scenario,
        compare_inline_count=args.compare_inline_count,
        since=since,
    )

    if args.report_json:
        Path(args.report_json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    for w in result.get("warnings") or []:
        print(f"WARN: {w}")

    if result.get("ok"):
        print(
            f"OK OCR publish (notes={result.get('ocr_note_count')}, "
            f"inline={result.get('inline_count')})"
        )
        return 0
    for err in result.get("errors") or ["assert failed"]:
        print(f"FAIL: {err}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

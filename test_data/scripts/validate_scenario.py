#!/usr/bin/env python3
"""校验 L3 场景评审结果：分数区间、关键词、变更文件命中。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "test_data" / "fixtures" / "scenarios"
INDEX_MANIFEST = FIXTURES / "manifest.yaml"
BUG_SCENARIOS = frozenset({
    "S02_npe_optional",
    "S03_empty_catch",
    "S04_hardcoded_secret",
    "S05_feign_no_timeout",
    "S06_incremental",
})


def load_scenario_index() -> dict[str, dict]:
    with open(INDEX_MANIFEST, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {s["id"]: s for s in data.get("scenarios", [])}


def load_scenario_files(scenario_id: str) -> list[str]:
    manifest = FIXTURES / scenario_id / "manifest.yaml"
    if not manifest.is_file():
        return []
    with open(manifest, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [item["dest"] for item in data.get("files", []) if item.get("dest")]


def collect_review_text(review: dict) -> str:
    parts: list[str] = [str(review.get("summary") or "")]
    for issue in review.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        parts.append(str(issue.get("message") or issue.get("title") or ""))
        parts.append(str(issue.get("file") or issue.get("path") or ""))
        parts.append(str(issue.get("category") or ""))
    return "\n".join(parts).lower()


def issue_paths(review: dict) -> list[str]:
    paths: list[str] = []
    for issue in review.get("issues") or []:
        if not isinstance(issue, dict):
            continue
        p = issue.get("file") or issue.get("path") or ""
        if p:
            paths.append(str(p).replace("\\", "/"))
    return paths


def validate_scenario_result(
    scenario_id: str,
    review: dict,
    *,
    tolerance: float = 5.0,
    require_file_hit: bool | None = None,
) -> dict[str, Any]:
    """返回 {ok, errors, warnings, checks}。"""
    index = load_scenario_index()
    spec = index.get(scenario_id)
    if not spec:
        return {"ok": False, "errors": [f"unknown scenario: {scenario_id}"], "warnings": [], "checks": {}}

    errors: list[str] = []
    warnings: list[str] = []
    checks: dict[str, Any] = {"scenario_id": scenario_id}

    if review.get("error"):
        errors.append(str(review["error"]))
    if not review.get("review_completed"):
        errors.append("review_completed=false")

    score = review.get("score")
    checks["score"] = score
    if score is None:
        errors.append("missing score")
    else:
        try:
            score_f = float(score)
        except (TypeError, ValueError):
            errors.append(f"invalid score: {score}")
            score_f = None
        if score_f is not None:
            lo = float(spec.get("expected_score_min", 0)) - tolerance
            hi = float(spec.get("expected_score_max", 100)) + tolerance
            checks["score_range"] = [lo, hi]
            out_of_range = not (lo <= score_f <= hi)
            if out_of_range:
                msg = (
                    f"score {score_f} outside [{lo}, {hi}] "
                    f"(spec {spec.get('expected_score_min')}-{spec.get('expected_score_max')} ±{tolerance})"
                )
                if spec.get("relax_score"):
                    warnings.append(msg)
                else:
                    errors.append(msg)

    text = collect_review_text(review)
    keywords = [str(kw) if kw is not None else "null" for kw in (spec.get("must_find_keywords") or [])]
    missing_kw = [kw for kw in keywords if kw.lower() not in text]
    checks["keywords_required"] = keywords
    checks["keywords_missing"] = missing_kw
    if missing_kw:
        errors.append(f"keywords not found: {missing_kw}")

    any_keywords = [
        str(kw) if kw is not None else "null" for kw in (spec.get("must_find_any_keywords") or [])
    ]
    if any_keywords:
        matched_any = [kw for kw in any_keywords if kw.lower() in text]
        checks["keywords_any_required"] = any_keywords
        checks["keywords_any_matched"] = matched_any
        if not matched_any:
            errors.append(f"none of keywords matched (need any of): {any_keywords}")

    changed_files = load_scenario_files(scenario_id)
    checks["changed_files"] = changed_files
    paths = issue_paths(review)
    checks["issue_paths"] = paths

    need_file = require_file_hit if require_file_hit is not None else scenario_id in BUG_SCENARIOS
    if need_file and changed_files:
        hit = any(
            any(cf in p or p.endswith(cf.split("/")[-1]) for p in paths)
            for cf in changed_files
        )
        checks["file_hit"] = hit
        if not hit:
            msg = f"no issue on changed files: {changed_files}"
            if paths:
                msg = f"issues present but none on changed files: {changed_files}"
            errors.append(msg)

    ok = len(errors) == 0
    return {"ok": ok, "errors": errors, "warnings": warnings, "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate L3 scenario review JSON")
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--review-json", required=True, help="Path to review result JSON")
    parser.add_argument("--tolerance", type=float, default=5.0)
    parser.add_argument("--report-json", metavar="PATH", help="Write validation report")
    parser.add_argument("--no-file-hit", action="store_true")
    args = parser.parse_args()

    review_path = Path(args.review_json)
    review = json.loads(review_path.read_text(encoding="utf-8-sig"))
    result = validate_scenario_result(
        args.scenario_id,
        review,
        tolerance=args.tolerance,
        require_file_hit=not args.no_file_hit,
    )
    result["scenario_id"] = args.scenario_id
    result["review_json"] = str(review_path)

    if args.report_json:
        out = Path(args.report_json)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    for w in result.get("warnings") or []:
        print(f"WARNING: {w}", file=sys.stderr)
    if result["ok"]:
        print(f"OK scenario {args.scenario_id}", file=sys.stderr)
        return 0
    score = review.get("score")
    completed = review.get("review_completed")
    print(
        f"  review: score={score} review_completed={completed} "
        f"http_status={review.get('http_status', '—')}",
        file=sys.stderr,
    )
    if review.get("failure_reason"):
        print(f"  failure_reason: {review['failure_reason']}", file=sys.stderr)
    if review.get("error"):
        print(f"  review.error: {review['error']}", file=sys.stderr)
    summary = (review.get("summary") or "").strip()
    if summary:
        if len(summary) > 240:
            summary = summary[:240] + "…"
        print(f"  summary: {summary}", file=sys.stderr)
    for err in result["errors"]:
        print(f"FAIL: {err}", file=sys.stderr)
    print(
        f"  详见: {args.report_json or review_path} 与同目录 validate.json；"
        f"可运行 aicr-reviewer/scripts/scenario_failure_report.py --scenario-dir {review_path.parent}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

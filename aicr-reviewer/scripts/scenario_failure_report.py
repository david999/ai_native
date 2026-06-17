#!/usr/bin/env python3
"""L3 场景失败诊断：打印 review/validate/MR 详情，便于排查。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
TEST_SCRIPTS = REPO_ROOT / "test_data" / "scripts"


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (json.JSONDecodeError, OSError):
        return None


def diagnose_scenario_dir(scen_dir: Path, *, scenario_id: str = "") -> dict:
    scen_dir = Path(scen_dir)
    review = _read_json(scen_dir / "review.json") or {}
    validate = _read_json(scen_dir / "validate.json") or {}
    mr = _read_json(scen_dir / "mr.json") or {}
    apply = _read_json(scen_dir / "apply.json") or {}
    sid = scenario_id or validate.get("scenario_id") or review.get("scenario_id") or scen_dir.name

    issues = review.get("issues") or []
    issue_lines = []
    for i, item in enumerate(issues[:5], start=1):
        if not isinstance(item, dict):
            continue
        issue_lines.append(
            f"    {i}. [{item.get('severity', '?')}] "
            f"{item.get('file') or item.get('path', '?')}:"
            f"{item.get('line', '?')} — "
            f"{(item.get('message') or item.get('title') or '')[:120]}"
        )

    summary = (review.get("summary") or "").strip()
    if len(summary) > 400:
        summary = summary[:400] + "…"

    hints: list[str] = []
    if review.get("error"):
        hints.append("review.json 含 error → 查 /review HTTP 状态、AICR 控制台或 acceptance.log")
    if review.get("review_completed") is False:
        hints.append("review_completed=false → 多为 LLM/GitLab 异常或 fail-open；查 AICR 日志")
    if review.get("http_status") and int(review["http_status"]) >= 400:
        hints.append(f"HTTP {review['http_status']} → 查鉴权 REVIEW_API_ALLOW_INSECURE / REVIEW_API_SECRET")
    for err in validate.get("errors") or []:
        if "keywords not found" in str(err):
            hints.append("关键词未命中 → 对比 manifest must_find_keywords 与 review summary/issues")
        if "changed files" in str(err) or "file_hit" in str(err):
            hints.append("变更文件未命中 → LLM issue 未指向 fixture 修改路径")
        if "outside" in str(err) and "score" in str(err):
            hints.append("分数越界 → 查 LLM 输出质量；S01 为 relax_score 时仅 WARNING")
    if not hints:
        hints.append("打开 validate.json / review.json 与 GitLab MR diff 对照")

    return {
        "scenario_id": sid,
        "scenario_dir": str(scen_dir),
        "mr_url": mr.get("web_url", ""),
        "project_id": mr.get("project_id"),
        "mr_iid": mr.get("mr_iid"),
        "branch": (apply.get("scenarios") or [{}])[0].get("branch") if apply else "",
        "review": {
            "score": review.get("score"),
            "review_completed": review.get("review_completed"),
            "http_status": review.get("http_status"),
            "failure_reason": review.get("failure_reason", ""),
            "error": review.get("error", ""),
            "summary": summary,
            "issue_count": len(issues),
            "issue_preview": issue_lines,
            "system_template": review.get("system_template") or review.get("system_template_requested", ""),
        },
        "validate": {
            "ok": validate.get("ok"),
            "errors": validate.get("errors") or [],
            "warnings": validate.get("warnings") or [],
            "checks": validate.get("checks") or {},
        },
        "hints": hints,
        "artifacts": {
            "review_json": str(scen_dir / "review.json"),
            "validate_json": str(scen_dir / "validate.json"),
            "mr_json": str(scen_dir / "mr.json"),
        },
    }


def format_diagnosis_text(d: dict) -> str:
    lines = [
        f"=== 场景失败诊断: {d['scenario_id']} ===",
        f"证据目录: {d['scenario_dir']}",
    ]
    if d.get("mr_url"):
        lines.append(f"MR: {d['mr_url']}")
    if d.get("project_id"):
        lines.append(f"GitLab: project_id={d['project_id']} mr_iid={d.get('mr_iid')}")
    if d.get("branch"):
        lines.append(f"分支: {d['branch']}")

    r = d["review"]
    lines.extend(
        [
            "",
            "[review.json]",
            f"  score: {r.get('score')}",
            f"  review_completed: {r.get('review_completed')}",
            f"  http_status: {r.get('http_status', '—')}",
        ]
    )
    if r.get("failure_reason"):
        lines.append(f"  failure_reason: {r['failure_reason']}")
    if r.get("error"):
        lines.append(f"  error: {r['error']}")
    if r.get("system_template"):
        lines.append(f"  template: {r['system_template']}")
    if r.get("summary"):
        lines.append(f"  summary: {r['summary']}")
    lines.append(f"  issues: {r.get('issue_count', 0)} 条")
    lines.extend(r.get("issue_preview") or [])

    v = d["validate"]
    lines.append("")
    lines.append("[validate.json]")
    lines.append(f"  ok: {v.get('ok')}")
    for err in v.get("errors") or []:
        lines.append(f"  ERROR: {err}")
    for warn in v.get("warnings") or []:
        lines.append(f"  WARNING: {warn}")
    checks = v.get("checks") or {}
    if checks.get("keywords_missing"):
        lines.append(f"  keywords_missing: {checks['keywords_missing']}")
    if "file_hit" in checks:
        lines.append(f"  file_hit: {checks['file_hit']}")
    if checks.get("changed_files"):
        lines.append(f"  changed_files: {checks['changed_files']}")

    lines.append("")
    lines.append("排查建议:")
    for i, h in enumerate(d.get("hints") or [], start=1):
        lines.append(f"  {i}. {h}")
    lines.append("")
    lines.append("产物路径:")
    for k, p in (d.get("artifacts") or {}).items():
        lines.append(f"  {k}: {p}")
    return "\n".join(lines)


def print_diagnosis(scen_dir: Path, *, scenario_id: str = "", write_md: bool = False) -> dict:
    d = diagnose_scenario_dir(scen_dir, scenario_id=scenario_id)
    text = format_diagnosis_text(d)
    print(text, file=sys.stderr)
    if write_md:
        out = Path(scen_dir) / "failure.zh.md"
        out.write_text(text + "\n", encoding="utf-8")
    return d


def main() -> int:
    ap = argparse.ArgumentParser(description="Print L3 scenario failure diagnostics")
    ap.add_argument("--scenario-dir", required=True)
    ap.add_argument("--scenario-id", default="")
    ap.add_argument("--write-md", action="store_true", help="Write failure.zh.md in scenario dir")
    ap.add_argument("--report-json", default="", help="Write machine-readable diagnosis JSON")
    args = ap.parse_args()

    d = print_diagnosis(
        Path(args.scenario_dir),
        scenario_id=args.scenario_id,
        write_md=args.write_md,
    )
    if args.report_json:
        Path(args.report_json).write_text(
            json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

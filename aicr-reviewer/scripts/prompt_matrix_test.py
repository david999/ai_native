#!/usr/bin/env python3
"""对指定 MR 按 prompts/variants/manifest.yaml 逐模板调用 /review 并生成对比报告。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

_SCRIPTS = Path(__file__).resolve().parent
_AICR = _SCRIPTS.parent
_REPO = _AICR.parent
_VARIANTS_MANIFEST = _AICR / "app" / "review" / "prompts" / "variants" / "manifest.yaml"


def load_dotenv() -> None:
    if str(_AICR) not in sys.path:
        sys.path.insert(0, str(_AICR))
    from app.env_loader import apply_monorepo_env

    apply_monorepo_env()


def _parse_http_error_body(raw: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return raw.strip() or "HTTP error"
    detail = data.get("detail")
    if isinstance(detail, list):
        return "; ".join(str(item) for item in detail)
    return str(detail or raw)


def post_review(
    base_url: str,
    project_id: int,
    mr_iid: int,
    *,
    system_template: str,
    secret: str,
    force_full: bool,
) -> dict:
    body = {
        "project_id": project_id,
        "mr_iid": mr_iid,
        "force_full": force_full,
    }
    if system_template:
        body["system_template"] = system_template
    data = json.dumps(body).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-AICR-Secret"] = secret
    req = urllib.request.Request(
        f"{base_url.rstrip('/')}/review",
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
            payload["http_status"] = resp.status
            return payload
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        detail = _parse_http_error_body(raw)
        return {
            "http_status": e.code,
            "error": f"HTTP Error {e.code}: {detail}",
            "review_completed": False,
            "score": 0,
            "issues": [],
        }
    except urllib.error.URLError as e:
        return {
            "http_status": 0,
            "error": str(e.reason or e),
            "review_completed": False,
            "score": 0,
            "issues": [],
        }


def load_variants() -> list[dict]:
    with open(_VARIANTS_MANIFEST, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("variants", [])


def template_ok(result: dict) -> tuple[bool, str]:
    """L3 验收成功条件：无 error、HTTP<400、且 review_completed=true。

    HTTP 200 但 review_completed=false（API fail-open）在验收矩阵中视为失败。
    """
    if result.get("error"):
        return False, str(result["error"])
    if result.get("http_status") and int(result["http_status"]) >= 400:
        return False, f"HTTP {result['http_status']}"
    if not result.get("review_completed"):
        reason = result.get("summary") or "review_completed=false"
        return False, reason
    return True, ""


def issue_preview(issues: list, limit: int = 3) -> list[dict]:
    rows = []
    for item in issues[:limit]:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "severity": item.get("severity", ""),
                "file": item.get("file", item.get("path", "")),
                "line": item.get("line", ""),
                "message": (item.get("message") or item.get("title") or "")[:200],
            }
        )
    return rows


def write_comparison_md(path: Path, rows: list[dict]) -> None:
    lines = [
        "# Prompt template comparison",
        "",
        "| template | ok | http | score | review_completed | issues | prompt_sha256 | error |",
        "|----------|----|------|-------|------------------|--------|---------------|-------|",
    ]
    for r in rows:
        ok = "yes" if r.get("ok") else "no"
        err = (r.get("failure_reason") or r.get("error") or "").replace("|", "/")[:80]
        sha = r.get("prompt_sha256") or ""
        lines.append(
            f"| {r['template_id']} | {ok} | {r.get('http_status', '')} | "
            f"{r.get('score', '')} | {r.get('review_completed', '')} | "
            f"{len(r.get('issues', []))} | {sha[:12]} | {err} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="Multi-template review matrix (L3 acceptance)",
        epilog=(
            "Success per template: review_completed=true. "
            "HTTP 200 fail-open responses count as failure for L3."
        ),
    )
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--mr-iid", type=int, required=True)
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--scenario-id", default="")
    parser.add_argument("--output-dir", required=True, help="Directory for per-template JSON + comparison.md")
    parser.add_argument("--force-full", action="store_true")
    parser.add_argument("--templates", nargs="*", help="Variant ids; default all from manifest")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    secret = os.environ.get("REVIEW_API_SECRET", "")

    variants = load_variants()
    variant_desc = {v["id"]: v.get("description", "") for v in variants}
    if args.templates:
        variants = [v for v in variants if v["id"] in args.templates]

    if not variants:
        print("No templates to review", file=sys.stderr)
        return 1

    rows: list[dict] = []
    failed = 0
    for v in variants:
        tid = v["id"]
        print(f"Review with template {tid}...")
        result = post_review(
            args.base_url,
            args.project_id,
            args.mr_iid,
            system_template=tid,
            secret=secret,
            force_full=args.force_full,
        )
        ok, failure_reason = template_ok(result)
        if not ok:
            failed += 1
            print(f"  FAILED: {failure_reason}", file=sys.stderr)
        else:
            print(
                f"  OK score={result.get('score')} issues={len(result.get('issues', []))} "
                f"completed={result.get('review_completed')}"
            )

        result["template_id"] = tid
        result["scenario_id"] = args.scenario_id
        result["template_description"] = variant_desc.get(tid, "")
        result["ok"] = ok
        result["failure_reason"] = failure_reason
        result["issue_preview"] = issue_preview(result.get("issues") or [])
        rows.append(result)
        with open(out_dir / f"{tid}.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    write_comparison_md(out_dir / "comparison.md", rows)
    summary = {
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "scenario_id": args.scenario_id,
        "project_id": args.project_id,
        "mr_iid": args.mr_iid,
        "base_url": args.base_url,
        "ok": failed == 0,
        "passed": len(rows) - failed,
        "failed": failed,
        "templates": [r["template_id"] for r in rows],
        "results": [
            {
                "template_id": r["template_id"],
                "template_description": r.get("template_description", ""),
                "ok": r.get("ok"),
                "http_status": r.get("http_status"),
                "error": r.get("error", ""),
                "failure_reason": r.get("failure_reason", ""),
                "score": r.get("score"),
                "review_completed": r.get("review_completed"),
                "issue_count": len(r.get("issues", [])),
                "summary": (r.get("summary") or "")[:500],
                "system_template": r.get("system_template", ""),
                "system_template_requested": r.get(
                    "system_template_requested", r["template_id"]
                ),
                "prompt_sha256": r.get("prompt_sha256", ""),
                "issue_preview": r.get("issue_preview", []),
            }
            for r in rows
        ],
    }
    with open(out_dir / "matrix_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Matrix report written to {out_dir} ({summary['passed']}/{len(rows)} passed)")
    if failed:
        print(f"Matrix failed: {failed} template(s) did not complete review", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

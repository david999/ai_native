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
    env_path = _REPO / "evn" / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())


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
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_variants() -> list[dict]:
    with open(_VARIANTS_MANIFEST, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("variants", [])


def write_comparison_md(path: Path, rows: list[dict]) -> None:
    lines = [
        "# Prompt template comparison",
        "",
        "| template | score | review_completed | issues | prompt_sha256 |",
        "|----------|-------|------------------|--------|---------------|",
    ]
    for r in rows:
        lines.append(
            f"| {r['template_id']} | {r.get('score', '')} | "
            f"{r.get('review_completed', '')} | {len(r.get('issues', []))} | "
            f"{r.get('prompt_sha256', '')[:12]} |"
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Multi-template review matrix")
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
    if args.templates:
        variants = [v for v in variants if v["id"] in args.templates]

    rows = []
    for v in variants:
        tid = v["id"]
        print(f"Review with template {tid}...")
        try:
            result = post_review(
                args.base_url,
                args.project_id,
                args.mr_iid,
                system_template=tid,
                secret=secret,
                force_full=args.force_full,
            )
        except urllib.error.URLError as e:
            result = {"error": str(e), "review_completed": False, "score": 0, "issues": []}
        result["template_id"] = tid
        result["scenario_id"] = args.scenario_id
        rows.append(result)
        with open(out_dir / f"{tid}.json", "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

    write_comparison_md(out_dir / "comparison.md", rows)
    summary = {
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "scenario_id": args.scenario_id,
        "project_id": args.project_id,
        "mr_iid": args.mr_iid,
        "templates": [r["template_id"] for r in rows],
        "results": [
            {
                "template_id": r["template_id"],
                "score": r.get("score"),
                "review_completed": r.get("review_completed"),
                "issue_count": len(r.get("issues", [])),
                "system_template": r.get("system_template", ""),
                "system_template_requested": r.get(
                    "system_template_requested", r["template_id"]
                ),
            }
            for r in rows
        ],
    }
    with open(out_dir / "matrix_summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"Matrix report written to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

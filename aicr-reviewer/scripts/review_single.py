#!/usr/bin/env python3
"""单次 POST /review，输出 JSON（L3 场景循环用）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_AICR = _SCRIPTS.parent
if str(_AICR) not in sys.path:
    sys.path.insert(0, str(_AICR))
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from prompt_matrix_test import load_dotenv, post_review, template_ok

DEFAULT_TEMPLATE = "system_spring_v1_baseline"


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Single /review call")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--mr-iid", type=int, required=True)
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--system-template", default=DEFAULT_TEMPLATE)
    parser.add_argument("--force-full", action="store_true")
    parser.add_argument("--no-force-full", action="store_true", help="Explicit incremental (force_full=false)")
    parser.add_argument("--output", required=True, help="Output JSON path")
    parser.add_argument("--scenario-id", default="")
    args = parser.parse_args()

    force_full = args.force_full
    if args.no_force_full:
        force_full = False

    secret = os.environ.get("REVIEW_API_SECRET", "")
    result = post_review(
        args.base_url,
        args.project_id,
        args.mr_iid,
        system_template=args.system_template,
        secret=secret,
        force_full=force_full,
    )
    ok, failure_reason = template_ok(result)
    result["scenario_id"] = args.scenario_id
    result["ok"] = ok
    result["failure_reason"] = failure_reason

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    if ok:
        print(f"OK review score={result.get('score')} issues={len(result.get('issues') or [])}")
        return 0
    print(f"FAIL: {failure_reason}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

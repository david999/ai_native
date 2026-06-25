"""OCR Gateway E2E 跑后报告采集。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

E2E_ROOT = Path(__file__).resolve().parent
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from lib.gitlab_api import REPO_ROOT, get_job_trace, gitlab_token, load_dotenv
from lib.scenario_manifest import get_scenario_spec
from wait_for_review import find_latest_review_job

RESULTS_ROOT = REPO_ROOT / "test-results"


def write_report_md(data: dict, out_dir: Path) -> str:
    lines = [
        "# OCR Gateway E2E 验收报告",
        "",
        f"- 场景: `{data.get('scenario_id')}`",
        f"- 时间: {data.get('timestamp')}",
        f"- MR: {data.get('mr_web_url') or 'n/a'}",
        f"- Gateway job: `{data.get('gateway_job_id')}` → **{data.get('gateway_status')}**",
        f"- CI job `code-review`: **{data.get('ci_job_status')}**",
        f"- OpenCodeReview notes: {data.get('ocr_note_count', 0)}",
        f"- Inline comments: {data.get('inline_count', 0)}",
        "",
        "## 断言",
        "",
    ]
    assert_result = data.get("assert") or {}
    if assert_result.get("ok"):
        lines.append("- 结果: **通过**")
    else:
        lines.append("- 结果: **失败**")
        for err in assert_result.get("errors") or []:
            lines.append(f"  - {err}")
    for w in assert_result.get("warnings") or []:
        lines.append(f"  - WARN: {w}")
    lines.extend(["", "## 产物", "", f"- `{out_dir / 'scenario.json'}`", f"- `{out_dir / 'job_log.txt'}`"])
    text = "\n".join(lines) + "\n"
    (out_dir / "ocr_e2e_report.zh.md").write_text(text, encoding="utf-8")
    return text


def collect_report(
    *,
    scenario_id: str,
    project_id: int,
    mr_iid: int,
    mr_web_url: str,
    apply_result: dict,
    mr_result: dict,
    wait_result: dict,
    gateway_result: dict,
    assert_result: dict,
    out_dir: Path,
) -> dict:
    token = gitlab_token()
    trace = wait_result.get("trace") or ""
    if not trace and token:
        job = find_latest_review_job(token, project_id, mr_iid)
        if job:
            trace = get_job_trace(token, project_id, int(job["id"]))

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "scenario.json").write_text(
        json.dumps({"apply": apply_result, "mr": mr_result}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    (out_dir / "job_log.txt").write_text(trace, encoding="utf-8")
    (out_dir / "gateway_job.json").write_text(
        json.dumps(gateway_result or {}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "assert.json").write_text(
        json.dumps(assert_result or {}, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    data = {
        "scenario_id": scenario_id,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mr_web_url": mr_web_url,
        "gateway_job_id": wait_result.get("gateway_job_id"),
        "gateway_status": (gateway_result or {}).get("status"),
        "gateway_message": (gateway_result or {}).get("message"),
        "ci_job_status": (wait_result.get("job") or {}).get("status"),
        "ocr_note_count": (assert_result or {}).get("ocr_note_count"),
        "inline_count": (assert_result or {}).get("inline_count"),
        "assert": assert_result,
        "spec_title": get_scenario_spec(scenario_id).get("title"),
    }
    write_report_md(data, out_dir)
    return data


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Write OCR E2E report bundle")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--mr-iid", type=int, required=True)
    parser.add_argument("--mr-web-url", default="")
    parser.add_argument("--apply-json", required=True)
    parser.add_argument("--mr-json", required=True)
    parser.add_argument("--wait-json", required=True)
    parser.add_argument("--gateway-json", default="")
    parser.add_argument("--assert-json", required=True)
    parser.add_argument("--output-dir", default="")
    args = parser.parse_args()

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_dir = Path(args.output_dir) if args.output_dir else RESULTS_ROOT / f"ocr-e2e-{ts}-{args.scenario}"

    def _load(path: str) -> dict:
        if not path:
            return {}
        return json.loads(Path(path).read_text(encoding="utf-8"))

    collect_report(
        scenario_id=args.scenario,
        project_id=args.project_id,
        mr_iid=args.mr_iid,
        mr_web_url=args.mr_web_url,
        apply_result=_load(args.apply_json),
        mr_result=_load(args.mr_json),
        wait_result=_load(args.wait_json),
        gateway_result=_load(args.gateway_json),
        assert_result=_load(args.assert_json),
        out_dir=out_dir,
    )
    print(f"Report: {out_dir / 'ocr_e2e_report.zh.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

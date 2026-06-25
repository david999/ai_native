"""Wait for MR pipeline code-review job to finish and return trace."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

E2E_ROOT = Path(__file__).resolve().parent
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from lib.gitlab_api import (
    get_job_trace,
    get_mr_pipelines,
    get_pipeline_jobs,
    gitlab_token,
    load_dotenv,
)
from poll_gateway_job import parse_gateway_job_id

REVIEW_JOB_NAME = "code-review"


def find_latest_review_job(
    token: str,
    project_id: int,
    mr_iid: int,
    *,
    commit_sha: str | None = None,
) -> dict | None:
    pipelines = get_mr_pipelines(token, project_id, mr_iid)
    if not pipelines:
        return None
    pipelines.sort(key=lambda p: p.get("id", 0), reverse=True)
    if commit_sha:
        pipelines = [p for p in pipelines if p.get("sha") == commit_sha]
        if not pipelines:
            return None
    for pipe in pipelines:
        jobs = get_pipeline_jobs(token, project_id, int(pipe["id"]))
        for job in jobs:
            if job.get("name") == REVIEW_JOB_NAME:
                return job
    return None


def wait_for_review_job(
    token: str,
    project_id: int,
    mr_iid: int,
    *,
    commit_sha: str | None = None,
    timeout_sec: int = 1500,
    interval_sec: int = 15,
) -> dict:
    deadline = time.time() + timeout_sec
    last_job: dict | None = None
    while time.time() < deadline:
        job = find_latest_review_job(
            token, project_id, mr_iid, commit_sha=commit_sha
        )
        if job:
            last_job = job
            status = job.get("status", "")
            print(f"Pipeline job {REVIEW_JOB_NAME} #{job.get('id')}: {status}")
            if status in ("success", "failed", "canceled", "skipped"):
                trace = get_job_trace(token, project_id, int(job["id"]))
                gateway_job_id = parse_gateway_job_id(trace)
                return {
                    "job": job,
                    "trace": trace,
                    "gateway_job_id": gateway_job_id,
                    "pipeline_id": job.get("pipeline", {}).get("id") if isinstance(job.get("pipeline"), dict) else job.get("pipeline"),
                }
        time.sleep(interval_sec)
    raise TimeoutError(
        f"No terminal '{REVIEW_JOB_NAME}' job for MR !{mr_iid} within {timeout_sec}s (last={last_job})"
    )


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Wait for datacalc-web code-review CI job")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--mr-iid", type=int, required=True)
    parser.add_argument("--timeout-sec", type=int, default=1500)
    parser.add_argument("--interval-sec", type=int, default=15)
    parser.add_argument("--report-json", metavar="PATH")
    args = parser.parse_args()

    token = gitlab_token()
    if not token:
        print("FAIL: no AICR_BOT_TOKEN / ROOT_PAT", file=sys.stderr)
        return 1

    try:
        result = wait_for_review_job(
            token,
            args.project_id,
            args.mr_iid,
            timeout_sec=args.timeout_sec,
            interval_sec=args.interval_sec,
        )
    except TimeoutError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if args.report_json:
        out = {
            "job": result["job"],
            "gateway_job_id": result.get("gateway_job_id"),
            "pipeline_id": result.get("pipeline_id"),
            "trace_len": len(result.get("trace") or ""),
        }
        Path(args.report_json).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        trace_path = Path(args.report_json).with_name("job_log.txt")
        trace_path.write_text(result.get("trace") or "", encoding="utf-8")

    if not result.get("gateway_job_id"):
        print("WARN: gateway job_id not found in CI trace", file=sys.stderr)

    ci_status = (result.get("job") or {}).get("status")
    if ci_status == "success":
        print(f"OK CI job {REVIEW_JOB_NAME} success")
        return 0
    print(f"FAIL CI job {REVIEW_JOB_NAME} status={ci_status}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

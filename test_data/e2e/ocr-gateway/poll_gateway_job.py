"""Parse Gateway job_id from CI job trace and poll until terminal state."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
from pathlib import Path

E2E_ROOT = Path(__file__).resolve().parent
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from lib.gitlab_api import gateway_get_job, load_dotenv

JOB_ID_RE = re.compile(r"Gateway job_id=([^\s\"']+)", re.I)
JOB_ID_JSON_RE = re.compile(r'"job_id"\s*:\s*"([^"]+)"')


def parse_gateway_job_id(log_text: str) -> str | None:
    m = JOB_ID_RE.search(log_text)
    if m:
        return m.group(1).strip()
    m = JOB_ID_JSON_RE.search(log_text)
    if m:
        return m.group(1).strip()
    return None


def poll_gateway_job(
    job_id: str,
    *,
    timeout_sec: int = 1200,
    interval_sec: int = 10,
) -> dict:
    deadline = time.time() + timeout_sec
    last: dict = {}
    while time.time() < deadline:
        last = gateway_get_job(job_id)
        status = last.get("status", "")
        print(f"Gateway job {job_id}: {status} — {last.get('message', '')}")
        if status in ("success", "failed"):
            return last
        time.sleep(interval_sec)
    raise TimeoutError(f"Gateway job {job_id} not terminal after {timeout_sec}s (last={last})")


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Poll OCR Gateway job status")
    parser.add_argument("--job-id", required=True)
    parser.add_argument("--timeout-sec", type=int, default=1200)
    parser.add_argument("--interval-sec", type=int, default=10)
    parser.add_argument("--report-json", metavar="PATH")
    args = parser.parse_args()

    try:
        result = poll_gateway_job(
            args.job_id,
            timeout_sec=args.timeout_sec,
            interval_sec=args.interval_sec,
        )
    except TimeoutError as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    except urllib.error.HTTPError as exc:
        print(f"FAIL: Gateway HTTP {exc.code}", file=sys.stderr)
        return 1

    if args.report_json:
        Path(args.report_json).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    if result.get("status") == "success":
        print(f"OK Gateway job {args.job_id}")
        return 0
    print(f"FAIL Gateway job {args.job_id}: {result.get('message')}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

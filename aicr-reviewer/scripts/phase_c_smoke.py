#!/usr/bin/env python3
"""L3-Full Phase C 抽检：/describe、/changelog、Webhook Note。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
_AICR = _SCRIPTS.parent
if str(_AICR) not in sys.path:
    sys.path.insert(0, str(_AICR))

from prompt_matrix_test import load_dotenv


def _headers(secret: str) -> dict:
    h = {"Content-Type": "application/json"}
    if secret:
        h["X-AICR-Secret"] = secret
    return h


def _post(base: str, path: str, body: dict, secret: str, timeout: int = 120) -> tuple[int, dict | str]:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        f"{base.rstrip('/')}{path}",
        data=data,
        headers=_headers(secret),
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def _webhook_note(base: str, project_id: int, mr_iid: int, token: str) -> tuple[int, dict | str]:
    payload = {
        "object_kind": "note",
        "object_attributes": {
            "noteable_type": "MergeRequest",
            "note": "@aicr 请用一句话说明这个 MR 的风险",
        },
        "merge_request": {"iid": mr_iid},
        "project": {"id": project_id},
        "user": {"username": "dev"},
    }
    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Gitlab-Token"] = token
    req = urllib.request.Request(
        f"{base.rstrip('/')}/webhook/gitlab",
        data=data,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw


def run_phase_c_smoke(project_id: int, mr_iid: int, base_url: str) -> dict:
    secret = os.environ.get("REVIEW_API_SECRET", "")
    webhook_secret = os.environ.get("GITLAB_WEBHOOK_SECRET", "")
    allow_insecure = os.environ.get("GITLAB_WEBHOOK_ALLOW_INSECURE", "0") == "1"

    results = []
    ok = True

    for name, path, body in (
        ("describe", "/describe", {"project_id": project_id, "mr_iid": mr_iid, "update_mr": False}),
        ("changelog", "/changelog", {"project_id": project_id, "mr_iid": mr_iid}),
    ):
        status, payload = _post(base_url, path, body, secret)
        entry = {"name": name, "http_status": status, "ok": status == 200}
        if isinstance(payload, dict):
            entry["body"] = payload
        else:
            entry["error"] = str(payload)[:300]
        if status != 200:
            ok = False
        results.append(entry)

    if webhook_secret or allow_insecure:
        w_status, w_body = _webhook_note(base_url, project_id, mr_iid, webhook_secret)
        entry = {
            "name": "webhook_note",
            "http_status": w_status,
            "ok": w_status == 200 and isinstance(w_body, dict) and w_body.get("status") == "accepted",
            "body": w_body if isinstance(w_body, dict) else str(w_body)[:300],
        }
        if not entry["ok"]:
            ok = False
        results.append(entry)
    else:
        results.append({
            "name": "webhook_note",
            "ok": True,
            "skipped": True,
            "reason": "no GITLAB_WEBHOOK_SECRET and GITLAB_WEBHOOK_ALLOW_INSECURE=0",
        })

    return {
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "ok": ok,
        "project_id": project_id,
        "mr_iid": mr_iid,
        "checks": results,
    }


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Phase C smoke for L3-full")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--mr-iid", type=int, required=True)
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--report-json", required=True)
    args = parser.parse_args()

    report = run_phase_c_smoke(args.project_id, args.mr_iid, args.base_url)
    Path(args.report_json).write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if report["ok"]:
        print("OK phase C smoke")
        return 0
    print("FAIL phase C smoke", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""通过 GitLab API 创建或查找 MR，输出 project_id 与 mr_iid（ocr-ci2 独立仓版）。"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from env_loader import load_dotenv, resolve_gitlab_token  # noqa: E402


def api_request(method: str, url: str, token: str, data: dict | None = None) -> dict | list:
    headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def find_project_id(gitlab_url: str, token: str, path: str) -> int:
    encoded = urllib.parse.quote(path, safe="")
    url = f"{gitlab_url.rstrip('/')}/api/v4/projects/{encoded}"
    proj = api_request("GET", url, token)
    return int(proj["id"])


def find_or_create_mr(
    gitlab_url: str,
    token: str,
    project_id: int,
    source_branch: str,
    target_branch: str,
    title: str,
) -> dict:
    base = f"{gitlab_url.rstrip('/')}/api/v4/projects/{project_id}/merge_requests"
    q = urllib.parse.urlencode(
        {"source_branch": source_branch, "target_branch": target_branch, "state": "opened"}
    )
    existing = api_request("GET", f"{base}?{q}", token)
    if existing:
        return existing[0]
    return api_request(
        "POST",
        base,
        token,
        {
            "source_branch": source_branch,
            "target_branch": target_branch,
            "title": title,
            "remove_source_branch": False,
        },
    )


def _gitlab_token() -> str:
    return resolve_gitlab_token()


def main() -> int:
    parser = argparse.ArgumentParser(description="Create or find GitLab MR")
    parser.add_argument("--project-path", default="java_group/datacalc-web")
    parser.add_argument("--source-branch", required=True)
    parser.add_argument("--target-branch", default="master")
    parser.add_argument("--title", default="OCR E2E test MR")
    parser.add_argument("--report-json", metavar="PATH")
    parser.add_argument("--env-file", help="Optional .env (overrides default env files)")
    args = parser.parse_args()

    if args.env_file:
        load_dotenv(env_file=args.env_file)
    else:
        load_dotenv()

    gitlab_url = os.environ.get("GITLAB_URL", "http://localhost:8000")
    token = _gitlab_token()
    if not token:
        print(
            "AICR_BOT_TOKEN, ROOT_PAT, or GITLAB_API_TOKEN required "
            "(env / OCR_CI2_ENV_FILE / ~/.opencodereview/config.json)",
            file=sys.stderr,
        )
        return 1

    project_id = find_project_id(gitlab_url, token, args.project_path)
    mr = find_or_create_mr(
        gitlab_url,
        token,
        project_id,
        args.source_branch,
        args.target_branch,
        args.title,
    )
    result = {
        "project_id": project_id,
        "mr_iid": mr["iid"],
        "web_url": mr.get("web_url", ""),
        "source_branch": args.source_branch,
        "target_branch": args.target_branch,
    }
    print(json.dumps(result, ensure_ascii=False))

    if args.report_json:
        with open(args.report_json, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

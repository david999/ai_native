#!/usr/bin/env python3
"""Live test: post [HIGH]/[MEDIUM] note to GitLab MR and verify Plan B markup."""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
_ACCEPTANCE = SCRIPTS / "acceptance"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(_ACCEPTANCE) not in sys.path:
    sys.path.insert(0, str(_ACCEPTANCE))

from env_loader import load_dotenv, resolve_gitlab_token  # noqa: E402
from gitlab_mr import GitLabMrClient, colorize_severity, post_review_from_files

PREFERRED_BRANCH = "ocr-test/D05_rule_severity_prefix"


def _gitlab_url() -> str:
    return os.environ.get("GITLAB_URL", "http://localhost:8000").rstrip("/")


def _project_path() -> str:
    return os.environ.get("OCR_TEST_PROJECT_PATH", "java_group/datacalc-web")


def _preferred_branch() -> str:
    return os.environ.get("OCR_TEST_MR_BRANCH", PREFERRED_BRANCH)


def _token() -> str:
    return resolve_gitlab_token()


def _api_get(url: str, token: str) -> dict | list:
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _project_id(token: str) -> int:
    enc = urllib.parse.quote(_project_path(), safe="")
    data = _api_get(f"{_gitlab_url()}/api/v4/projects/{enc}", token)
    return int(data["id"])


def _pick_mr_iid(token: str, project_id: int) -> tuple[int, str]:
    open_mrs = _api_get(
        f"{_gitlab_url()}/api/v4/projects/{project_id}/merge_requests?state=opened&per_page=50",
        token,
    )
    if not isinstance(open_mrs, list):
        raise RuntimeError("failed to list open MRs")

    branch = _preferred_branch()
    for mr in open_mrs:
        if mr.get("source_branch") == branch:
            return int(mr["iid"]), str(mr.get("web_url") or "")

    if open_mrs:
        mr = open_mrs[0]
        return int(mr["iid"]), str(mr.get("web_url") or "")

    raise RuntimeError(f"no open MR in {_project_path()}")


def _latest_note_body(token: str, project_id: int, mr_iid: int) -> str:
    notes = _api_get(
        f"{_gitlab_url()}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes?sort=desc&order_by=created_at&per_page=5",
        token,
    )
    if not isinstance(notes, list) or not notes:
        return ""
    return str(notes[0].get("body") or "")


def main() -> int:
    if os.environ.get("OCR_TEST_LIVE", "").lower() not in ("1", "true", "yes"):
        print("SKIP: set OCR_TEST_LIVE=1 to post test notes to GitLab MR", file=sys.stderr)
        return 0

    load_dotenv()
    token = _token()
    if not token:
        print("FAIL: no GitLab token (AICR_BOT_TOKEN / GITLAB_API_TOKEN / config.json)", file=sys.stderr)
        return 1

    project_id = _project_id(token)
    mr_iid, mr_url = _pick_mr_iid(token, project_id)
    print(f"Target MR: {_project_path()} !{mr_iid} ({mr_url or 'n/a'})")

    client = GitLabMrClient(
        gitlab_url=_gitlab_url(),
        project_id=str(project_id),
        mr_iid=str(mr_iid),
        api_token=token,
    )

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    marker = f"ocr-severity-color-test-{ts}"

    # 1) 直接 note：Plan B emoji + strong
    note_body = (
        f"**OpenCodeReview severity color test** `{marker}`\n\n"
        + colorize_severity("[HIGH] Automated HIGH severity verification.\n\n")
        + colorize_severity("[MEDIUM] Automated MEDIUM severity verification.")
    )
    resp = client.post_note(note_body)
    if not resp.get("success"):
        print(f"FAIL: post_note rejected: {resp}", file=sys.stderr)
        return 1
    print("OK: posted test note")

    fetched = _latest_note_body(token, project_id, mr_iid)
    checks = {
        "marker_in_note": marker in fetched,
        "high_emoji": "🔴" in fetched and "[HIGH]" in fetched,
        "medium_emoji": "🟡" in fetched and "[MEDIUM]" in fetched,
        "strong_tag": "<strong>" in fetched,
    }
    for name, ok in checks.items():
        print(f"  {'OK' if ok else 'FAIL'}: {name}")

    if not all(checks.values()):
        print("FAIL: Plan B markup not found in latest MR note body", file=sys.stderr)
        print("--- note body preview ---")
        print(fetched[:800])
        return 1

    # 2) post_review_from_files 路径（fallback summary 含着色）
    import tempfile

    result = {
        "comments": [
            {
                "path": "",
                "start_line": 0,
                "end_line": 0,
                "content": "[HIGH] fallback path HIGH",
            },
            {
                "path": "",
                "start_line": 0,
                "end_line": 0,
                "content": "[MEDIUM] fallback path MEDIUM",
            },
        ],
        "warnings": [],
    }
    with tempfile.TemporaryDirectory() as tmp:
        result_path = Path(tmp) / "ocr-result.json"
        result_path.write_text(json.dumps(result), encoding="utf-8")
        os.environ.pop("OCR_POST_STRICT", None)
        code = post_review_from_files(client, result_path=str(result_path))
        if code != 0:
            print(f"WARN: post_review_from_files exit {code} (may still have posted fallback)")

    notes = _api_get(
        f"{_gitlab_url()}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes?sort=desc&order_by=created_at&per_page=10",
        token,
    )
    fallback_ok = False
    if isinstance(notes, list):
        for note in notes:
            body = str(note.get("body") or "")
            if "fallback path HIGH" in body and "🔴" in body and "fallback path MEDIUM" in body:
                fallback_ok = True
                break

    print(f"  {'OK' if fallback_ok else 'FAIL'}: fallback_summary_color")
    if not fallback_ok:
        print("FAIL: fallback summary note missing Plan B markup", file=sys.stderr)
        return 1

    print("PASS: GitLab severity color Plan B verified")
    base = mr_url or f"{_gitlab_url()}/{_project_path()}/-/merge_requests/{mr_iid}"
    print(f"View MR: {base}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

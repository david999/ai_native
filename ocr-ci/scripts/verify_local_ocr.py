#!/usr/bin/env python3
"""Local verification: ~/.opencodereview/config.json + installed ocr CLI path.

Does not print secrets. Optional: post a marker note to an open MR.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from ocr_ci_config import resolve_gitlab_api_token, user_config_path

_OCR_CI_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_REPO = _OCR_CI_ROOT.parent / "test_data" / "spring-cloud-demo"
_DEFAULT_RESULT = _OCR_CI_ROOT / ".build" / "ocr-result.json"


def _ocr_executable() -> str:
    """Resolve ocr on Windows (ocr.cmd) and Unix."""
    for name in ("ocr.cmd", "ocr.exe", "ocr"):
        path = shutil.which(name)
        if path:
            return path
    return "ocr"


def _gitlab_get(url: str, token: str) -> object:
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _gitlab_post_note(base: str, project_id: str, mr_iid: str, token: str, body: str) -> int:
    payload = json.dumps({"body": body}).encode()
    req = urllib.request.Request(
        f"{base}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/notes",
        data=payload,
        headers={"PRIVATE-TOKEN": token, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode())
    return int(data["id"])


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify local OCR + config.json gitlab token")
    parser.add_argument("--gitlab-url", default="http://localhost:8000")
    parser.add_argument("--project", default="java_group/spring-cloud-demo")
    parser.add_argument("--mr-iid", default="7")
    parser.add_argument("--repo", type=Path, default=_DEFAULT_REPO)
    parser.add_argument("--from-ref", default="origin/main")
    parser.add_argument("--to-ref", default="HEAD")
    parser.add_argument("--result-out", type=Path, default=_DEFAULT_RESULT)
    parser.add_argument("--post-verify-note", action="store_true")
    args = parser.parse_args()

    ok = True

    ocr_bin = _ocr_executable()

    # 1) OCR CLI
    try:
        ver = subprocess.run([ocr_bin, "version"], capture_output=True, text=True, check=True)
        first = (ver.stdout or "").strip().splitlines()[0]
        print(f"ocr_cli: ok ({first})")
    except (FileNotFoundError, subprocess.CalledProcessError) as exc:
        print(f"ocr_cli: FAIL ({exc})")
        ok = False

    # 2) config.json
    cfg_path = user_config_path()
    token = resolve_gitlab_api_token()
    print(f"config_path: {cfg_path}")
    print(f"gitlab.api_token: {'set' if token else 'unset'}")
    if not token:
        ok = False

    # 3) GitLab user
    if token:
        try:
            user = _gitlab_get(f"{args.gitlab_url.rstrip('/')}/api/v4/user", token)
            print(f"gitlab_user: {user.get('username')} (id={user.get('id')})")
        except urllib.error.URLError as exc:
            print(f"gitlab_user: FAIL ({exc})")
            ok = False

    # 4) ocr review (local)
    args.result_out.parent.mkdir(parents=True, exist_ok=True)
    review_cmd = [
        ocr_bin,
        "review",
        "--from",
        args.from_ref,
        "--to",
        args.to_ref,
        "--format",
        "json",
        "--audience",
        "agent",
        "--concurrency",
        "2",
    ]
    try:
        proc = subprocess.run(
            review_cmd,
            cwd=args.repo,
            capture_output=True,
            text=True,
            check=True,
            timeout=600,
        )
        result = json.loads(proc.stdout)
        args.result_out.write_text(proc.stdout, encoding="utf-8")
        print(
            f"ocr_review: status={result.get('status')} "
            f"comments={len(result.get('comments') or [])} "
            f"warnings={len(result.get('warnings') or [])}"
        )
        if result.get("status") != "success":
            ok = False
    except (subprocess.CalledProcessError, json.JSONDecodeError, subprocess.TimeoutExpired) as exc:
        print(f"ocr_review: FAIL ({exc})")
        ok = False

    # 5) MR API (post prerequisites)
    project_enc = args.project.replace("/", "%2F")
    if token:
        try:
            proj = _gitlab_get(f"{args.gitlab_url.rstrip('/')}/api/v4/projects/{project_enc}", token)
            pid = str(proj["id"])
            versions = _gitlab_get(
                f"{args.gitlab_url.rstrip('/')}/api/v4/projects/{pid}/merge_requests/{args.mr_iid}/versions",
                token,
            )
            print(f"mr_iid={args.mr_iid} versions={len(versions)} project_id={pid}")
            if args.post_verify_note and args.result_out.is_file():
                result = json.loads(args.result_out.read_text(encoding="utf-8"))
                note = (
                    "[local-ocr-verify] "
                    f"status={result.get('status')} comments={len(result.get('comments') or [])} "
                    "— gitlab.api_token from ~/.opencodereview/config.json"
                )
                note_id = _gitlab_post_note(args.gitlab_url.rstrip("/"), pid, args.mr_iid, token, note)
                print(f"posted_verify_note_id: {note_id}")
        except urllib.error.HTTPError as exc:
            print(f"gitlab_mr_api: FAIL HTTP {exc.code}")
            ok = False
        except urllib.error.URLError as exc:
            print(f"gitlab_mr_api: FAIL ({exc})")
            ok = False

    print("overall:", "PASS" if ok else "FAIL")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()

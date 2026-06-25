#!/usr/bin/env python3
"""OCR Gateway + datacalc-web 单场景 E2E 编排。"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

E2E_ROOT = Path(__file__).resolve().parent
REPO_ROOT = E2E_ROOT.parents[2]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from assert_ocr_publish import assert_ocr_publish
from assert_ocr_session import assert_ocr_session
from collect_report import collect_report
from lib.gitlab_api import gitlab_token, load_dotenv
from lib.scenario_manifest import get_scenario_spec, load_scenario_ids
from poll_gateway_job import poll_gateway_job
from wait_for_review import wait_for_review_job

PROJECT_PATH = "java_group/datacalc-web"
VERIFY_SCRIPT = REPO_ROOT / "test_data" / "scripts" / "verify_l3b_runner.ps1"
CREATE_MR_SCRIPT = REPO_ROOT / "test_data" / "scripts" / "create_or_update_mr.py"
RESULTS_ROOT = REPO_ROOT / "test-results"

# D02 inline count cached for D04 compare within same -All run
_compare_inline: dict[str, int] = {}


def run_py(script: str, args: list[str]) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(E2E_ROOT / script), *args]
    print(f"+ {' '.join(cmd)}")
    return subprocess.run(cmd, check=False)


def run_preflight() -> int:
    if not VERIFY_SCRIPT.is_file():
        print(f"FAIL: missing preflight script {VERIFY_SCRIPT}", file=sys.stderr)
        return 1
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(VERIFY_SCRIPT),
        "-ProjectPath",
        PROJECT_PATH,
        "-OcrGatewayOnly",
    ]
    print(f"+ {' '.join(cmd)}")
    return subprocess.run(cmd, check=False).returncode


def create_or_update_mr(
    *,
    branch: str,
    target_branch: str,
    title: str,
    report_path: Path,
) -> dict | None:
    if not CREATE_MR_SCRIPT.is_file():
        print(f"FAIL: missing {CREATE_MR_SCRIPT}", file=sys.stderr)
        return None
    cmd = [
        sys.executable,
        str(CREATE_MR_SCRIPT),
        "--project-path",
        PROJECT_PATH,
        "--source-branch",
        branch,
        "--target-branch",
        target_branch,
        "--title",
        title,
        "--report-json",
        str(report_path),
    ]
    print(f"+ {' '.join(cmd)}")
    proc = subprocess.run(cmd, check=False, text=True, capture_output=True)
    if proc.stdout:
        print(proc.stdout.rstrip())
    if proc.stderr:
        print(proc.stderr.rstrip(), file=sys.stderr)
    if proc.returncode != 0:
        return None
    if report_path.is_file():
        return json.loads(report_path.read_text(encoding="utf-8"))
    try:
        return json.loads(proc.stdout.strip())
    except json.JSONDecodeError:
        return None


def run_scenario(scenario_id: str, *, skip_preflight: bool) -> int:
    load_dotenv()
    if not skip_preflight:
        code = run_preflight()
        if code != 0:
            print("FAIL: preflight checks failed", file=sys.stderr)
            return code

    spec = get_scenario_spec(scenario_id)
    target_branch = spec.get("target_branch", "master")
    branch = spec.get("branch", f"ocr-test/{scenario_id}")

    with tempfile.TemporaryDirectory(prefix="ocr-e2e-") as tmp:
        tmp_path = Path(tmp)
        apply_json = tmp_path / "apply.json"
        mr_json = tmp_path / "mr.json"
        wait_json = tmp_path / "wait.json"
        gateway_json = tmp_path / "gateway.json"
        session_assert_json = tmp_path / "session_assert.json"
        assert_json = tmp_path / "assert.json"

        code = run_py(
            "apply_scenario.py",
            ["--scenario", scenario_id, "--report-json", str(apply_json)],
        ).returncode
        if code != 0:
            return code

        apply_data = json.loads(apply_json.read_text(encoding="utf-8"))["scenarios"][0]
        if not gitlab_token():
            print("FAIL: no GitLab token", file=sys.stderr)
            return 1

        title = f"OCR E2E {scenario_id}"
        mr_result = create_or_update_mr(
            branch=branch,
            target_branch=target_branch,
            title=title,
            report_path=mr_json,
        )
        if not mr_result:
            print("FAIL: create_or_update_mr failed", file=sys.stderr)
            return 1
        mr_result["project_path"] = PROJECT_PATH
        project_id = int(mr_result["project_id"])
        mr_json.write_text(json.dumps(mr_result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"MR !{mr_result['mr_iid']}: {mr_result.get('web_url')}")

        # Only count OpenCodeReview posts from this run (not prior MR history).
        assert_since = datetime.now(timezone.utc) - timedelta(seconds=15)

        try:
            wait_result = wait_for_review_job(
                gitlab_token(),
                project_id,
                int(mr_result["mr_iid"]),
                commit_sha=apply_data.get("commit_sha"),
            )
        except TimeoutError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1

        ci_job = wait_result.get("job") or {}
        ci_status = ci_job.get("status", "")
        if ci_status != "success":
            print(
                f"FAIL: CI job code-review status={ci_status} (expected success)",
                file=sys.stderr,
            )
            return 1

        gateway_job_id = wait_result.get("gateway_job_id")
        if not gateway_job_id:
            print(
                "FAIL: gateway job_id not found in CI trace; cannot verify Gateway review",
                file=sys.stderr,
            )
            return 1

        wait_payload = {
            "job": wait_result["job"],
            "gateway_job_id": gateway_job_id,
            "trace": wait_result.get("trace"),
            "pipeline_id": wait_result.get("pipeline_id"),
        }
        wait_json.write_text(json.dumps(wait_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        (tmp_path / "job_log.txt").write_text(wait_result.get("trace") or "", encoding="utf-8")

        gateway_result: dict = {}
        try:
            gateway_result = poll_gateway_job(gateway_job_id)
        except TimeoutError as exc:
            print(f"FAIL: {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"FAIL: Gateway poll: {exc}", file=sys.stderr)
            return 1
        gateway_json.write_text(
            json.dumps(gateway_result, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if gateway_result.get("status") != "success":
            print(
                f"FAIL: Gateway job {gateway_job_id} status={gateway_result.get('status')}",
                file=sys.stderr,
            )
            return 1

        compare_inline = None
        compare_sid = spec.get("compare_scenario")
        if compare_sid and compare_sid in _compare_inline:
            compare_inline = _compare_inline[compare_sid]

        session_assert_result = assert_ocr_session(gateway_job_id, scenario_id)
        session_assert_json.write_text(
            json.dumps(session_assert_result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        assert_result = assert_ocr_publish(
            project_id,
            int(mr_result["mr_iid"]),
            scenario_id,
            compare_inline_count=compare_inline,
            since=assert_since,
        )
        assert_json.write_text(json.dumps(assert_result, indent=2, ensure_ascii=False), encoding="utf-8")

        if session_assert_result.get("viewer_hint"):
            print(f"OCR Viewer: {session_assert_result['viewer_hint']}")
        for w in session_assert_result.get("warnings") or []:
            print(f"WARN (session): {w}")

        if scenario_id == "D02_bug_npe_optional":
            _compare_inline[scenario_id] = assert_result.get("inline_count", 0)

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out_dir = RESULTS_ROOT / f"ocr-e2e-{ts}-{scenario_id}"
        collect_report(
            scenario_id=scenario_id,
            project_id=project_id,
            mr_iid=int(mr_result["mr_iid"]),
            mr_web_url=mr_result.get("web_url") or "",
            apply_result=apply_data,
            mr_result=mr_result,
            wait_result=wait_payload,
            gateway_result=gateway_result,
            assert_result=assert_result,
            session_assert_result=session_assert_result,
            out_dir=out_dir,
        )

        if not session_assert_result.get("ok") and not session_assert_result.get("skipped"):
            for err in session_assert_result.get("errors") or []:
                print(f"FAIL (session): {err}", file=sys.stderr)
            return 1

        if not assert_result.get("ok"):
            for err in assert_result.get("errors") or []:
                print(f"FAIL: {err}", file=sys.stderr)
            return 1

        print(f"OK scenario {scenario_id}")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR Gateway datacalc-web E2E")
    parser.add_argument("--scenario", help="Scenario id e.g. D01_feature_date_guard")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--skip-preflight", action="store_true")
    args = parser.parse_args()

    ids = load_scenario_ids(args.all, args.scenario)
    failed = 0
    for sid in ids:
        print(f"\n=== OCR E2E {sid} ===")
        if run_scenario(sid, skip_preflight=args.skip_preflight) != 0:
            failed += 1
            if not args.all:
                return 1

    if failed:
        print(f"\n{failed}/{len(ids)} scenario(s) failed", file=sys.stderr)
        return 1
    print(f"\nAll {len(ids)} scenario(s) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

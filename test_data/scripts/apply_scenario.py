#!/usr/bin/env python3
"""将 fixtures/scenarios/<id>/ 的固定文件应用到 spring-cloud-demo 并 push。"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "test_data" / "fixtures" / "scenarios"
DEMO_DIR = REPO_ROOT / "test_data" / "spring-cloud-demo"
BASE_BRANCH = "aicr-test-base"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print(f"+ {' '.join(cmd)}  (cwd={cwd})")
    result = subprocess.run(cmd, cwd=str(cwd), check=False, text=True, capture_output=True)
    if check and result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=err)
    return result


def load_scenario_ids(all_flag: bool, scenario: str | None, *, skip_incremental: bool = True) -> list[str]:
    manifest = FIXTURES / "manifest.yaml"
    with open(manifest, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    all_scenarios = data.get("scenarios", [])
    all_ids = [s["id"] for s in all_scenarios]
    scenarios = all_scenarios
    if skip_incremental:
        scenarios = [s for s in scenarios if not s.get("incremental_only")]
    ids = [s["id"] for s in scenarios]
    if all_flag:
        return ids
    if scenario:
        if scenario not in all_ids:
            raise SystemExit(f"Unknown scenario: {scenario}")
        return [scenario]
    raise SystemExit("Specify --scenario ID or --all")


def _safe_dest_path(rel_dest: str) -> Path:
    dest = (DEMO_DIR / rel_dest).resolve()
    demo_root = DEMO_DIR.resolve()
    if demo_root not in dest.parents and dest != demo_root:
        raise SystemExit(f"Unsafe dest path escapes demo repo: {rel_dest}")
    return dest


def _remote_branch_exists(branch: str) -> bool:
    result = run(
        ["git", "ls-remote", "--heads", "origin", branch],
        DEMO_DIR,
        check=False,
    )
    return bool(result.stdout.strip())


def _checkout_base_branch() -> None:
    run(["git", "fetch", "origin"], DEMO_DIR, check=False)
    local = run(["git", "rev-parse", "--verify", BASE_BRANCH], DEMO_DIR, check=False)
    if local.returncode != 0:
        run(["git", "checkout", "-B", BASE_BRANCH], DEMO_DIR)
        if _remote_branch_exists(BASE_BRANCH):
            run(["git", "push", "-u", "origin", BASE_BRANCH], DEMO_DIR, check=False)
        return

    run(["git", "checkout", BASE_BRANCH], DEMO_DIR)
    if _remote_branch_exists(BASE_BRANCH):
        run(["git", "reset", "--hard", f"origin/{BASE_BRANCH}"], DEMO_DIR)
    else:
        print(f"Warning: origin/{BASE_BRANCH} missing; using local {BASE_BRANCH}")


def apply_one(
    scenario_id: str,
    *,
    push: bool,
    target_branch: str | None,
    incremental: bool = False,
) -> dict:
    scen_dir = FIXTURES / scenario_id
    scen_manifest = scen_dir / "manifest.yaml"
    if not scen_manifest.is_file():
        raise SystemExit(f"Missing {scen_manifest}")

    with open(scen_manifest, encoding="utf-8") as f:
        scen = yaml.safe_load(f)

    branch = target_branch or scen.get("branch", f"aicr-test/{scenario_id}")
    commit_msg = scen.get("commit_message", f"test({scenario_id}): acceptance scenario")

    if not DEMO_DIR.is_dir():
        raise SystemExit(f"Demo not found: {DEMO_DIR}")

    if incremental:
        run(["git", "fetch", "origin"], DEMO_DIR, check=False)
        local = run(["git", "rev-parse", "--verify", branch], DEMO_DIR, check=False)
        if local.returncode != 0:
            raise SystemExit(f"Branch {branch} missing for incremental apply")
        run(["git", "checkout", branch], DEMO_DIR)
    else:
        _checkout_base_branch()
        run(["git", "checkout", "-B", branch], DEMO_DIR)

    for item in scen.get("files", []):
        rel_dest = item["dest"]
        src = scen_dir / item["source"]
        dest = _safe_dest_path(rel_dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        run(["git", "add", rel_dest], DEMO_DIR)

    status = run(["git", "status", "--porcelain"], DEMO_DIR)
    if not status.stdout.strip():
        if incremental:
            raise SystemExit(f"incremental apply for {scenario_id} produced no changes")
        print(f"No changes for {scenario_id}")
    else:
        run(["git", "commit", "-m", commit_msg], DEMO_DIR)

    sha = run(["git", "rev-parse", "HEAD"], DEMO_DIR).stdout.strip()

    if push:
        if incremental:
            run(["git", "push", "origin", branch], DEMO_DIR)
        else:
            run(["git", "push", "-f", "origin", branch], DEMO_DIR)

    return {
        "scenario_id": scenario_id,
        "branch": branch,
        "commit_sha": sha,
        "pushed": push,
        "files": [item["dest"] for item in scen.get("files", [])],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply acceptance scenario to spring-cloud-demo")
    parser.add_argument("--scenario", help="Scenario id e.g. S02_npe_optional")
    parser.add_argument("--all", action="store_true", help="Apply all scenarios sequentially")
    parser.add_argument("--no-push", action="store_true", help="Commit locally only")
    parser.add_argument("--branch", help="Override target branch name")
    parser.add_argument("--incremental", action="store_true", help="Commit on existing branch without base reset")
    parser.add_argument("--include-incremental", action="store_true", help="With --all, include S06_incremental")
    parser.add_argument("--report-json", metavar="PATH")
    args = parser.parse_args()

    ids = load_scenario_ids(
        args.all,
        args.scenario,
        skip_incremental=not args.include_incremental,
    )
    results = []
    for sid in ids:
        results.append(
            apply_one(
                sid,
                push=not args.no_push,
                target_branch=args.branch,
                incremental=args.incremental,
            )
        )

    if args.report_json:
        report_path = Path(args.report_json)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump({"scenarios": results}, f, indent=2, ensure_ascii=False)

    print(f"Applied {len(results)} scenario(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

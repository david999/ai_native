"""将 OCR E2E fixture 应用到 datacalc-web 并 push。"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

E2E_ROOT = Path(__file__).resolve().parent
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from lib.scenario_manifest import get_scenario_dir, load_scenario_ids

REPO_ROOT = E2E_ROOT.parents[2]
DATACALC_DIR = REPO_ROOT / "test_data" / "datacalc-web"
BASE_BRANCH = "ocr-test-base"
DEFAULT_TARGET = "master"


def run(cmd: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess:
    print(f"+ {' '.join(cmd)}  (cwd={cwd})")
    result = subprocess.run(cmd, cwd=str(cwd), check=False, text=True, capture_output=True)
    if check and result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        raise subprocess.CalledProcessError(result.returncode, cmd, output=result.stdout, stderr=err)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)
    return result


def _safe_dest_path(rel_dest: str) -> Path:
    dest = (DATACALC_DIR / rel_dest).resolve()
    demo_root = DATACALC_DIR.resolve()
    if demo_root not in dest.parents and dest != demo_root:
        raise SystemExit(f"Unsafe dest path escapes datacalc-web: {rel_dest}")
    return dest


def _remote_branch_exists(branch: str) -> bool:
    result = run(["git", "ls-remote", "--heads", "origin", branch], DATACALC_DIR, check=False)
    return bool(result.stdout.strip())


def _checkout_base_branch() -> None:
    run(["git", "fetch", "origin"], DATACALC_DIR, check=False)
    local = run(["git", "rev-parse", "--verify", BASE_BRANCH], DATACALC_DIR, check=False)
    if local.returncode != 0:
        run(["git", "checkout", "-B", BASE_BRANCH, DEFAULT_TARGET], DATACALC_DIR)
        run(["git", "push", "-u", "origin", BASE_BRANCH], DATACALC_DIR, check=False)
        return

    run(["git", "checkout", BASE_BRANCH], DATACALC_DIR)
    if _remote_branch_exists(BASE_BRANCH):
        run(["git", "reset", "--hard", f"origin/{BASE_BRANCH}"], DATACALC_DIR)
    elif _remote_branch_exists(DEFAULT_TARGET):
        print(
            f"origin/{BASE_BRANCH} missing; resetting local base to origin/{DEFAULT_TARGET}"
        )
        run(["git", "reset", "--hard", f"origin/{DEFAULT_TARGET}"], DATACALC_DIR)
        run(["git", "push", "-u", "origin", BASE_BRANCH], DATACALC_DIR, check=False)
    else:
        raise SystemExit(
            f"Cannot establish {BASE_BRANCH}: neither origin/{BASE_BRANCH} "
            f"nor origin/{DEFAULT_TARGET} exists"
        )


def apply_one(scenario_id: str, *, push: bool) -> dict:
    scen_dir = get_scenario_dir(scenario_id)
    scen_manifest = scen_dir / "manifest.yaml"
    if not scen_manifest.is_file():
        raise SystemExit(f"Missing {scen_manifest}")

    with open(scen_manifest, encoding="utf-8") as f:
        scen = yaml.safe_load(f)

    branch = scen.get("branch", f"ocr-test/{scenario_id}")
    commit_msg = scen.get("commit_message", f"test({scenario_id}): ocr e2e scenario")

    if not DATACALC_DIR.is_dir():
        raise SystemExit(f"datacalc-web not found: {DATACALC_DIR}")

    _checkout_base_branch()
    run(["git", "checkout", "-B", branch], DATACALC_DIR)

    for item in scen.get("files", []):
        rel_dest = item["dest"]
        src = scen_dir / item["source"]
        dest = _safe_dest_path(rel_dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        run(["git", "add", rel_dest], DATACALC_DIR)

    status = run(["git", "status", "--porcelain"], DATACALC_DIR)
    if not status.stdout.strip():
        raise SystemExit(
            f"No file changes for {scenario_id}; fixture already matches branch (re-run would not trigger new review)"
        )
    run(["git", "commit", "-m", commit_msg], DATACALC_DIR)

    sha = run(["git", "rev-parse", "HEAD"], DATACALC_DIR).stdout.strip()

    if push:
        run(["git", "push", "-f", "origin", branch], DATACALC_DIR)

    return {
        "scenario_id": scenario_id,
        "branch": branch,
        "commit_sha": sha,
        "pushed": push,
        "files": [item["dest"] for item in scen.get("files", [])],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply OCR E2E scenario to datacalc-web")
    parser.add_argument("--scenario", help="Scenario id e.g. D02_bug_npe_optional")
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--report-json", metavar="PATH")
    args = parser.parse_args()

    ids = load_scenario_ids(args.all, args.scenario)
    results = []
    for sid in ids:
        try:
            results.append(apply_one(sid, push=not args.no_push))
        except SystemExit as exc:
            if exc.code not in (0, None):
                return int(exc.code) if isinstance(exc.code, int) else 1
            raise

    if args.report_json:
        report_path = Path(args.report_json)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps({"scenarios": results}, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"Applied {len(results)} scenario(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

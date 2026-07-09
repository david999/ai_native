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

from lib.env_loader import load_dotenv
from lib.paths import get_datacalc_dir
from lib.scenario_manifest import get_scenario_dir, load_scenario_ids

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


def _safe_dest_path(datacalc_dir: Path, rel_dest: str) -> Path:
    dest = (datacalc_dir / rel_dest).resolve()
    demo_root = datacalc_dir.resolve()
    if demo_root not in dest.parents and dest != demo_root:
        raise SystemExit(f"Unsafe dest path escapes datacalc-web: {rel_dest}")
    return dest


def _remote_branch_exists(datacalc_dir: Path, branch: str) -> bool:
    result = run(["git", "ls-remote", "--heads", "origin", branch], datacalc_dir, check=False)
    return bool(result.stdout.strip())


def _checkout_base_branch(datacalc_dir: Path) -> None:
    run(["git", "fetch", "origin"], datacalc_dir, check=False)
    local = run(["git", "rev-parse", "--verify", BASE_BRANCH], datacalc_dir, check=False)
    if local.returncode != 0:
        run(["git", "checkout", "-B", BASE_BRANCH, DEFAULT_TARGET], datacalc_dir)
        run(["git", "push", "-u", "origin", BASE_BRANCH], datacalc_dir, check=False)
        return

    run(["git", "checkout", BASE_BRANCH], datacalc_dir)
    if _remote_branch_exists(datacalc_dir, BASE_BRANCH):
        run(["git", "reset", "--hard", f"origin/{BASE_BRANCH}"], datacalc_dir)
    elif _remote_branch_exists(datacalc_dir, DEFAULT_TARGET):
        print(
            f"origin/{BASE_BRANCH} missing; resetting local base to origin/{DEFAULT_TARGET}"
        )
        run(["git", "reset", "--hard", f"origin/{DEFAULT_TARGET}"], datacalc_dir)
        run(["git", "push", "-u", "origin", BASE_BRANCH], datacalc_dir, check=False)
    else:
        raise SystemExit(
            f"Cannot establish {BASE_BRANCH}: neither origin/{BASE_BRANCH} "
            f"nor origin/{DEFAULT_TARGET} exists"
        )


def apply_one(scenario_id: str, *, push: bool, datacalc_dir: Path) -> dict:
    scen_dir = get_scenario_dir(scenario_id)
    scen_manifest = scen_dir / "manifest.yaml"
    if not scen_manifest.is_file():
        raise SystemExit(f"Missing {scen_manifest}")

    with open(scen_manifest, encoding="utf-8") as f:
        scen = yaml.safe_load(f)

    branch = scen.get("branch", f"ocr-test/{scenario_id}")
    commit_msg = scen.get("commit_message", f"test({scenario_id}): ocr e2e scenario")

    if not datacalc_dir.is_dir():
        raise SystemExit(f"datacalc-web not found: {datacalc_dir}")

    _checkout_base_branch(datacalc_dir)
    run(["git", "checkout", "-B", branch], datacalc_dir)

    for item in scen.get("files", []):
        rel_dest = item["dest"]
        src = scen_dir / item["source"]
        dest = _safe_dest_path(datacalc_dir, rel_dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        run(["git", "add", rel_dest], datacalc_dir)

    status = run(["git", "status", "--porcelain"], datacalc_dir)
    if not status.stdout.strip():
        raise SystemExit(
            f"No file changes for {scenario_id}; fixture already matches branch (re-run would not trigger new review)"
        )
    run(["git", "commit", "-m", commit_msg], datacalc_dir)

    sha = run(["git", "rev-parse", "HEAD"], datacalc_dir).stdout.strip()

    if push:
        run(["git", "push", "-f", "origin", branch], datacalc_dir)

    return {
        "scenario_id": scenario_id,
        "branch": branch,
        "commit_sha": sha,
        "pushed": push,
        "files": [item["dest"] for item in scen.get("files", [])],
    }


def main() -> int:
    load_dotenv()
    datacalc_dir = get_datacalc_dir()

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
            results.append(apply_one(sid, push=not args.no_push, datacalc_dir=datacalc_dir))
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

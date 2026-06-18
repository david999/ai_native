#!/usr/bin/env python3
"""L3-standard / L3-full 场景套件编排（供 run_acceptance.sh 调用）。"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AICR_ROOT = REPO_ROOT / "aicr-reviewer"
SCRIPTS = AICR_ROOT / "scripts"
TEST_SCRIPTS = REPO_ROOT / "test_data" / "scripts"

STANDARD_SCENARIOS = [
    "S01_clean_refactor",
    "S02_npe_optional",
    "S03_empty_catch",
    "S04_hardcoded_secret",
    "S05_feign_no_timeout",
]

L3_FULL_SKIPPED_EXTRAS = [
    ("s02_matrix", "S02 三模板矩阵"),
    ("gitlab_publish", "GitLab 发帖（S02）"),
    ("ci_gate", "CI 门禁"),
    ("s06_incremental", "S06 增量评审"),
    ("phase_c", "Phase C 抽检"),
]


def _py() -> str:
    venv = AICR_ROOT / ".venv" / "bin" / "python"
    return str(venv if venv.is_file() else sys.executable)


def run_cmd(cmd: list[str], *, check: bool = True) -> int:
    print(f"+ {' '.join(cmd)}")
    r = subprocess.run(cmd, cwd=str(REPO_ROOT))
    if check and r.returncode != 0:
        raise SystemExit(r.returncode)
    return r.returncode


def evaluate_ci_gate(score, *, review_completed: bool, threshold: int | None = None) -> int:
    """与 ci_review_gate.sh 一致：仅 completed 且低分 → exit 1。"""
    threshold = int(threshold or os.environ.get("AICR_SCORE_THRESHOLD") or 60)
    if not review_completed:
        return 0
    if score is None or score == "":
        return 0
    return 1 if float(score) < threshold else 0


def scenario_baseline(
    scenario_id: str,
    l3_dir: Path,
    *,
    assert_publish: bool,
    branch_override: str = "",
) -> dict:
    scen_dir = l3_dir / scenario_id
    scen_dir.mkdir(parents=True, exist_ok=True)
    apply_report = scen_dir / "apply.json"
    apply_cmd = [
        _py(),
        str(TEST_SCRIPTS / "apply_scenario.py"),
        "--scenario",
        scenario_id,
        "--report-json",
        str(apply_report),
    ]
    if branch_override:
        apply_cmd += ["--branch", branch_override]
    run_cmd(apply_cmd)

    apply = json.loads(apply_report.read_text(encoding="utf-8"))
    branch = apply["scenarios"][0]["branch"]
    mr_report = scen_dir / "mr.json"
    run_cmd(
        [
            _py(),
            str(TEST_SCRIPTS / "create_or_update_mr.py"),
            "--source-branch",
            branch,
            "--target-branch",
            "main",
            "--title",
            f"AICR acceptance {scenario_id}",
            "--report-json",
            str(mr_report),
        ]
    )
    mr = json.loads(mr_report.read_text(encoding="utf-8"))
    review_json = scen_dir / "review.json"
    run_cmd(
        [
            _py(),
            str(SCRIPTS / "review_single.py"),
            "--project-id",
            str(mr["project_id"]),
            "--mr-iid",
            str(mr["mr_iid"]),
            "--force-full",
            "--output",
            str(review_json),
            "--scenario-id",
            scenario_id,
        ]
    )
    review = json.loads(review_json.read_text(encoding="utf-8"))
    validate_report = scen_dir / "validate.json"
    val_rc = run_cmd(
        [
            _py(),
            str(TEST_SCRIPTS / "validate_scenario.py"),
            "--scenario-id",
            scenario_id,
            "--review-json",
            str(review_json),
            "--report-json",
            str(validate_report),
            "--tolerance",
            "5",
        ],
        check=False,
    )
    if val_rc != 0:
        run_cmd(
            [
                _py(),
                str(SCRIPTS / "review_single.py"),
                "--project-id",
                str(mr["project_id"]),
                "--mr-iid",
                str(mr["mr_iid"]),
                "--force-full",
                "--output",
                str(review_json),
                "--scenario-id",
                scenario_id,
            ]
        )
        review = json.loads(review_json.read_text(encoding="utf-8"))
        val_rc = run_cmd(
            [
                _py(),
                str(TEST_SCRIPTS / "validate_scenario.py"),
                "--scenario-id",
                scenario_id,
                "--review-json",
                str(review_json),
                "--report-json",
                str(validate_report),
                "--tolerance",
                "5",
            ],
            check=False,
        )
    publish_ok = True
    if assert_publish and scenario_id == "S02_npe_optional":
        pub_report = scen_dir / "publish.json"
        pub_rc = run_cmd(
            [
                _py(),
                str(TEST_SCRIPTS / "assert_gitlab_publish.py"),
                "--project-id",
                str(mr["project_id"]),
                "--mr-iid",
                str(mr["mr_iid"]),
                "--expected-score",
                str(review.get("score", "")),
                "--report-json",
                str(pub_report),
            ],
            check=False,
        )
        publish_ok = pub_rc == 0
    val_ok = val_rc == 0
    return {
        "scenario_id": scenario_id,
        "score": review.get("score"),
        "validation_ok": val_ok,
        "publish_ok": publish_ok,
        "mr_url": mr.get("web_url", ""),
        "project_id": mr["project_id"],
        "mr_iid": mr["mr_iid"],
        "ok": val_ok and publish_ok,
    }


def setup_l3_env(*, skip_gitlab_infra: bool) -> bool:
    """GitLab ensure + demo bootstrap（计入 l3_env_setup 耗时）。"""
    if not skip_gitlab_infra:
        gl = TEST_SCRIPTS / "ensure_gitlab.sh"
        if gl.is_file():
            rc = run_cmd(["bash", str(gl)], check=False)
            if rc != 0:
                return False
    boot = TEST_SCRIPTS / "bootstrap_demo.sh"
    if boot.is_file():
        run_cmd(["bash", str(boot)])
    return True


def run_standard(
    l3_dir: Path,
    *,
    assert_publish: bool,
    timing,
    t_start=None,
    t_end=None,
    skip_gitlab_infra: bool = False,
) -> dict:
    def phase_start(pid: str, label: str) -> None:
        if t_start:
            t_start(pid, label)
        else:
            timing.start(pid, label)

    def phase_end(*, ok: bool = True, skipped: bool = False, reason: str = "") -> None:
        if t_end:
            t_end(ok=ok, skipped=skipped, reason=reason)
        else:
            timing.end(ok=ok, skipped=skipped, reason=reason)

    release: dict = {"scenarios": [], "warnings": [], "phases": {}}
    suite_ok = True
    phase_start("l3_env_setup", "L3 环境（GitLab + Demo）")
    env_ok = setup_l3_env(skip_gitlab_infra=skip_gitlab_infra)
    phase_end(ok=env_ok)
    if not env_ok:
        release["warnings"].append("L3 env setup failed (GitLab/Demo)")
        (l3_dir / "release_data.json").write_text(
            json.dumps(release, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return {"ok": False, "release": release, "env_failed": True}

    suite_t0 = time.perf_counter()
    for sid in STANDARD_SCENARIOS:
        print(f"=== Scenario {sid} (baseline) ===")
        phase_start(f"scenario_{sid}", f"场景 {sid} baseline")
        entry = scenario_baseline(sid, l3_dir, assert_publish=assert_publish)
        phase_end(ok=entry["ok"])
        release["scenarios"].append(entry)
        if not entry["ok"]:
            suite_ok = False
            release["warnings"].append(f"Scenario {sid} validation/publish failed")
            scen_dir = l3_dir / sid
            report_py = SCRIPTS / "scenario_failure_report.py"
            if report_py.is_file() and scen_dir.is_dir():
                run_cmd(
                    [
                        _py(),
                        str(report_py),
                        "--scenario-dir",
                        str(scen_dir),
                        "--scenario-id",
                        sid,
                        "--write-md",
                    ],
                    check=False,
                )
    suite_elapsed = int(time.perf_counter() - suite_t0)
    timing.phases.append(
        {
            "id": "scenario_suite",
            "label": "场景套件 S01–S05",
            "seconds": suite_elapsed,
            "ok": suite_ok,
            "ended": timing.phases[-1]["ended"] if timing.phases else "",
        }
    )
    release["phases"]["scenario_suite"] = {"ok": suite_ok}
    (l3_dir / "release_data.json").write_text(
        json.dumps(release, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return {"ok": suite_ok, "release": release}


def run_full_extras(
    l3_dir: Path,
    release: dict,
    s02: dict,
    timing,
    t_start=None,
    t_end=None,
) -> bool:
    def phase_start(pid: str, label: str) -> None:
        if t_start:
            t_start(pid, label)
        else:
            timing.start(pid, label)

    def phase_end(*, ok: bool = True, skipped: bool = False, reason: str = "") -> None:
        if t_end:
            t_end(ok=ok, skipped=skipped, reason=reason)
        else:
            timing.end(ok=ok, skipped=skipped, reason=reason)

    extras_ok = True
    phases = release.setdefault("phases", {})
    s02_mr = {"project_id": s02["project_id"], "mr_iid": s02["mr_iid"]}

    review_path = l3_dir / "S02_npe_optional" / "review.json"
    s02_review = json.loads(review_path.read_text(encoding="utf-8"))

    print("=== S02 prompt matrix ===")
    phase_start("s02_matrix", "S02 三模板矩阵")
    matrix_dir = l3_dir / "S02_npe_optional_matrix"
    matrix_rc = run_cmd(
        [
            _py(),
            str(SCRIPTS / "prompt_matrix_test.py"),
            "--project-id",
            str(s02_mr["project_id"]),
            "--mr-iid",
            str(s02_mr["mr_iid"]),
            "--scenario-id",
            "S02_npe_optional",
            "--output-dir",
            str(matrix_dir),
            "--force-full",
        ],
        check=False,
    )
    matrix_ok = matrix_rc == 0
    phases["s02_matrix"] = {"ok": matrix_ok}
    phase_end(ok=matrix_ok)
    if not matrix_ok:
        extras_ok = False
    ms = matrix_dir / "matrix_summary.json"
    if ms.is_file():
        release["matrix_summary"] = json.loads(ms.read_text(encoding="utf-8"))

    print("=== CI review gate (cached S02 score) ===")
    phase_start("ci_gate", "CI 门禁")
    gate_exit = evaluate_ci_gate(
        s02_review.get("score"),
        review_completed=bool(s02_review.get("review_completed")),
    )
    gate_ok = gate_exit == 1
    phases["ci_gate"] = {
        "ok": gate_ok,
        "exit_code": gate_exit,
        "expected_exit": 1,
        "cached": True,
        "cached_score": s02_review.get("score"),
        "cached_completed": bool(s02_review.get("review_completed")),
        "threshold": int(os.environ.get("AICR_SCORE_THRESHOLD") or 60),
    }
    phase_end(ok=gate_ok)
    if not gate_ok:
        extras_ok = False

    phase_start("gitlab_publish", "GitLab 发帖（S02）")
    pub_ok = bool(s02.get("publish_ok", False))
    phases["gitlab_publish"] = {"ok": pub_ok}
    phase_end(ok=pub_ok)
    if not pub_ok:
        extras_ok = False

    print("=== S06 incremental ===")
    phase_start("s06_incremental", "S06 增量评审")
    s06_branch = "aicr-test/S06_incremental"
    s06_dir = l3_dir / "S06_incremental"
    s06_dir.mkdir(parents=True, exist_ok=True)
    s06_ok = False
    if run_cmd(
        [
            _py(),
            str(TEST_SCRIPTS / "apply_scenario.py"),
            "--scenario",
            "S02_npe_optional",
            "--branch",
            s06_branch,
            "--report-json",
            str(s06_dir / "apply1.json"),
        ],
        check=False,
    ):
        extras_ok = False
        phase_end(ok=False)
        timing.add_skipped("phase_c", "Phase C 抽检", "S06 incremental failed")
        progress.end("phase_c", "Phase C 抽检", seconds=0, ok=False, skipped=True)
    else:
        run_cmd(
            [
                _py(),
                str(TEST_SCRIPTS / "create_or_update_mr.py"),
                "--source-branch",
                s06_branch,
                "--target-branch",
                "main",
                "--title",
                "AICR acceptance S06_incremental",
                "--report-json",
                str(s06_dir / "mr.json"),
            ]
        )
        s06_mr = json.loads((s06_dir / "mr.json").read_text(encoding="utf-8"))
        r1 = s06_dir / "review1.json"
        run_cmd(
            [
                _py(),
                str(SCRIPTS / "review_single.py"),
                "--project-id",
                str(s06_mr["project_id"]),
                "--mr-iid",
                str(s06_mr["mr_iid"]),
                "--force-full",
                "--output",
                str(r1),
                "--scenario-id",
                "S06_incremental",
            ]
        )
        first = json.loads(r1.read_text(encoding="utf-8"))
        run_cmd(
            [
                _py(),
                str(TEST_SCRIPTS / "apply_scenario.py"),
                "--scenario",
                "S06_incremental",
                "--branch",
                s06_branch,
                "--incremental",
                "--report-json",
                str(s06_dir / "apply2.json"),
            ]
        )
        r2 = s06_dir / "review2.json"
        second_rc = run_cmd(
            [
                _py(),
                str(SCRIPTS / "review_single.py"),
                "--project-id",
                str(s06_mr["project_id"]),
                "--mr-iid",
                str(s06_mr["mr_iid"]),
                "--no-force-full",
                "--output",
                str(r2),
                "--scenario-id",
                "S06_incremental",
            ],
            check=False,
        )
        second = json.loads(r2.read_text(encoding="utf-8"))
        val2 = run_cmd(
            [
                _py(),
                str(TEST_SCRIPTS / "validate_scenario.py"),
                "--scenario-id",
                "S06_incremental",
                "--review-json",
                str(r2),
                "--report-json",
                str(s06_dir / "validate2.json"),
                "--tolerance",
                "5",
            ],
            check=False,
        )
        s06_ok = second_rc == 0 and val2 == 0
        phases["s06_incremental"] = {"ok": s06_ok}
        release["incremental"] = {
            "first_score": first.get("score"),
            "first_sha": first.get("prompt_sha256"),
            "second_score": second.get("score"),
            "second_sha": second.get("prompt_sha256"),
            "second_ok": s06_ok,
        }
        phase_end(ok=s06_ok)
        if not s06_ok:
            extras_ok = False
            timing.add_skipped("phase_c", "Phase C 抽检", "S06 validation failed")
            progress.end("phase_c", "Phase C 抽检", seconds=0, ok=False, skipped=True)
        else:
            print("=== Phase C smoke ===")
            phase_start("phase_c", "Phase C 抽检")
            phase_rc = run_cmd(
                [
                    _py(),
                    str(SCRIPTS / "phase_c_smoke.py"),
                    "--project-id",
                    str(s06_mr["project_id"]),
                    "--mr-iid",
                    str(s06_mr["mr_iid"]),
                    "--report-json",
                    str(s06_dir / "phase_c.json"),
                ],
                check=False,
            )
            phases["phase_c"] = {"ok": phase_rc == 0}
            phase_end(ok=phase_rc == 0)
            if phase_rc != 0:
                extras_ok = False

    (l3_dir / "release_data.json").write_text(
        json.dumps(release, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return extras_ok


def add_full_skipped_extras(timing, reason: str = "scenario_suite failed") -> None:
    for phase_id, label in L3_FULL_SKIPPED_EXTRAS:
        timing.add_skipped(phase_id, label, reason)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-dir", required=True)
    parser.add_argument("--mode", choices=("standard", "full"), required=True)
    parser.add_argument(
        "--skip-gitlab-infra",
        action="store_true",
        help="Skip ensure_gitlab (preflight already brought GitLab up)",
    )
    args = parser.parse_args()

    if str(AICR_ROOT) not in sys.path:
        sys.path.insert(0, str(AICR_ROOT))
    from app.env_loader import apply_monorepo_env

    apply_monorepo_env()

    record_dir = Path(args.record_dir)
    l3_dir = record_dir / "l3"
    l3_dir.mkdir(parents=True, exist_ok=True)

    if args.mode == "full" and os.environ.get("REVIEW_DRY_RUN", "0") == "1":
        print("L3-full requires REVIEW_DRY_RUN=0", file=sys.stderr)
        return 1

    sys.path.insert(0, str(SCRIPTS))
    from acceptance_timing import ProgressReporter, TimingRecorder

    timing = TimingRecorder()
    level = "L3-full" if args.mode == "full" else "L3-standard"
    progress = ProgressReporter(level)
    progress.print_plan()

    def t_start(phase_id: str, label: str) -> None:
        timing.start(phase_id, label)
        progress.start(phase_id, label)

    def t_end(*, ok: bool = True, skipped: bool = False, reason: str = "") -> None:
        if not timing._current:
            return
        pid = timing._current["id"]
        label = timing._current["label"]
        timing.end(ok=ok, skipped=skipped, reason=reason)
        entry = timing.phases[-1] if timing.phases else {}
        progress.end(pid, label, seconds=int(entry.get("seconds") or 0), ok=ok, skipped=skipped)

    assert_pub = args.mode == "full"
    result = run_standard(
        l3_dir,
        assert_publish=assert_pub,
        timing=timing,
        t_start=t_start,
        t_end=t_end,
        skip_gitlab_infra=args.skip_gitlab_infra,
    )
    if result.get("env_failed"):
        if args.mode == "full":
            add_full_skipped_extras(timing)
            for pid, label in L3_FULL_SKIPPED_EXTRAS:
                progress.end(pid, label, seconds=0, ok=False, skipped=True)
        timing.write(record_dir / "timing.json")
        return 1
    if not result["ok"]:
        if args.mode == "full":
            add_full_skipped_extras(timing)
            for pid, label in L3_FULL_SKIPPED_EXTRAS:
                progress.end(pid, label, seconds=0, ok=False, skipped=True)
        timing.write(record_dir / "timing.json")
        return 1
    if args.mode == "standard":
        timing.write(record_dir / "timing.json")
        return 0

    release = result["release"]
    s02 = next(s for s in release["scenarios"] if s["scenario_id"] == "S02_npe_optional")
    release["phases"]["gitlab_publish"] = {"ok": s02.get("publish_ok", False)}
    if not s02.get("publish_ok"):
        add_full_skipped_extras(timing, "S02 GitLab publish failed")
        for pid, label in L3_FULL_SKIPPED_EXTRAS:
            progress.end(pid, label, seconds=0, ok=False, skipped=True)
        timing.write(record_dir / "timing.json")
        (l3_dir / "release_data.json").write_text(
            json.dumps(release, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return 1
    ok = run_full_extras(l3_dir, release, s02, timing, t_start=t_start, t_end=t_end)
    timing.write(record_dir / "timing.json")
    if not ok:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

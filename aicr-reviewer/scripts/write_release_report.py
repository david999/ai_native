#!/usr/bin/env python3
"""生成交付签收报告 release.zh.md（L3-full）。"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from acceptance_timing import (
    format_duration,
    gate_phases_for_level,
    load_timing,
    phase_by_id,
    phase_result_label,
)
from l3_report_common import (
    collect_scenario_dirs,
    discover_scenario_ids,
    load_scenario_index,
    mr_link,
    read_json,
    render_ci_gate_section,
    render_matrix_section,
    render_s06_section,
    render_scenario_detail_block,
    render_scenario_summary_table_row,
    scenario_artifacts,
)

DEFAULT_SCORE_THRESHOLD = 60


def _git_head(repo: Path) -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=str(repo),
            capture_output=True,
            text=True,
            check=False,
        )
        return (r.stdout or "").strip() or "unknown"
    except OSError:
        return "unknown"


def _failure_reason(record_dir: Path, scenario_id: str, scenario: dict) -> str:
    validate = read_json(record_dir / "l3" / scenario_id / "validate.json")
    if isinstance(validate, dict):
        errors = validate.get("errors") or []
        if errors:
            return "; ".join(str(e) for e in errors)
        checks = validate.get("checks") or {}
        missing = checks.get("keywords_missing") or []
        if missing:
            return f"keywords missing: {missing}"
    note = scenario.get("note") or ""
    if note:
        return str(note)
    if scenario.get("validation_ok") is False:
        return "校验未通过"
    if scenario.get("publish_ok") is False:
        return "GitLab 发帖未通过"
    return ""


def _gate_note(phase_id: str, release_phases: dict, timing_phase: dict | None) -> str:
    if timing_phase and timing_phase.get("skipped"):
        return str(timing_phase.get("reason") or "前置失败短路")
    rp = release_phases.get(phase_id) or {}
    if phase_id == "scenario_suite" and not rp:
        return ""
    if phase_id == "ci_gate" and rp:
        parts = []
        if rp.get("cached"):
            parts.append("S02 缓存分数")
        exp = rp.get("expected_exit")
        got = rp.get("exit_code")
        if exp is not None and got is not None:
            parts.append(f"exit {got}（预期 {exp}）")
        if rp.get("cached_score") is not None:
            parts.append(f"score={rp['cached_score']}")
        return "；".join(parts) if parts else ""
    if phase_id == "L1" and not rp:
        return ""
    if phase_id == "L2" and not rp:
        return ""
    return ""


def _collect_failures(
    record_dir: Path,
    release_data: dict,
    timing: dict | None,
    *,
    l1_ok: bool | None,
    l2_ok: bool | None,
) -> list[str]:
    failures: list[str] = []
    if l1_ok is False:
        failures.append("L1 冒烟未通过")
    if l2_ok is False:
        failures.append("L2 健康检查未通过")
    phases = release_data.get("phases") or {}
    for phase_id, label in gate_phases_for_level("L3-full"):
        if phase_id in ("L1", "L2"):
            continue
        tp = phase_by_id(timing, phase_id)
        if tp and tp.get("skipped"):
            continue
        rp = phases.get(phase_id)
        if rp is not None and not rp.get("ok", False):
            failures.append(f"{label}未通过")
    for s in release_data.get("scenarios") or []:
        if not s.get("validation_ok", True) or s.get("publish_ok") is False:
            sid = s.get("scenario_id", "")
            reason = _failure_reason(record_dir, sid, s)
            failures.append(f"{sid}：{reason or '校验/发帖失败'}")
    return failures


def _collect_skipped(timing: dict | None, level: str) -> list[str]:
    if not timing:
        return []
    gate_ids = {p[0] for p in gate_phases_for_level(level)}
    out: list[str] = []
    for p in timing.get("phases") or []:
        if p.get("skipped") and p.get("id") in gate_ids:
            reason = p.get("reason") or ""
            label = p.get("label") or p.get("id")
            out.append(f"{label}" + (f"（{reason}）" if reason else ""))
    return out


def _phase_duration(timing: dict | None, phase_id: str) -> str:
    p = phase_by_id(timing, phase_id)
    if not p:
        return "—"
    if p.get("skipped"):
        return "—"
    return format_duration(p.get("seconds"))


def _phase_result(
    phase_id: str,
    timing: dict | None,
    release_phases: dict,
    *,
    l1_ok: bool | None = None,
    l2_ok: bool | None = None,
) -> str:
    tp = phase_by_id(timing, phase_id)
    if tp and tp.get("skipped"):
        return "未执行"
    if phase_id == "L1" and l1_ok is not None:
        return "通过" if l1_ok else "失败"
    if phase_id == "L2" and l2_ok is not None:
        return "通过" if l2_ok else "失败"
    rp = release_phases.get(phase_id)
    if rp is None and tp is None:
        return "—"
    if tp:
        return phase_result_label(tp)
    if rp is not None:
        return "通过" if rp.get("ok") else "失败"
    return "—"


def write_release_md(record_dir: Path, *, level: str, failed: bool) -> str:
    record_dir = Path(record_dir)
    l3_dir = record_dir / "l3"
    meta = read_json(record_dir / "meta.json") or {}
    summary = read_json(record_dir / "summary.json") or {}
    l1 = read_json(record_dir / "l1-smoke.json") or {}
    l2 = read_json(record_dir / "l2-health.json") or {}
    release_data = read_json(l3_dir / "release_data.json") or {}
    timing = load_timing(record_dir)

    l1_ok = l1.get("failed", 1) == 0 if l1 else None
    l2_ok = l2.get("ok") if l2 else None
    release_phases = release_data.get("phases") or {}

    total_seconds = (timing or {}).get("total_seconds")
    total_label = format_duration(total_seconds) if total_seconds is not None else "—"
    failures = _collect_failures(
        record_dir, release_data, timing, l1_ok=l1_ok, l2_ok=l2_ok
    )
    skipped = _collect_skipped(timing, level)

    lines = [
        "# L3-Full 交付签收报告",
        "",
        f"- **交付结论：{'不通过' if failed else '通过'}**",
        f"- **总耗时：{total_label}**",
        f"- 验收层级：**{level}**",
        f"- 报告目录：`{record_dir}`",
        "",
    ]

    if failures:
        lines.append("### 失败项")
        lines.append("")
        for f in failures:
            lines.append(f"- {f}")
        lines.append("")

    if skipped:
        lines.append("### 未执行阶段")
        lines.append("")
        for s in skipped:
            lines.append(f"- {s}")
        lines.append("")

    lines.extend(
        [
            "## 门禁汇总",
            "",
            "| 阶段 | 结果 | 耗时 | 说明 |",
            "|------|------|------|------|",
        ]
    )

    for phase_id, label in gate_phases_for_level(level):
        if phase_id == "L1" and l1_ok is None:
            continue
        if phase_id == "L2" and l2_ok is None:
            continue
        if phase_id not in ("L1", "L2") and phase_id not in release_phases:
            tp = phase_by_id(timing, phase_id)
            if not tp:
                continue
        result = _phase_result(
            phase_id,
            timing,
            release_phases,
            l1_ok=l1_ok,
            l2_ok=l2_ok,
        )
        duration = _phase_duration(timing, phase_id)
        note = _gate_note(phase_id, release_phases, phase_by_id(timing, phase_id))
        if phase_id == "L1" and l1_ok is not None:
            note = f"{l1.get('passed', 0)}/{l1.get('total', 0)} 项"
        lines.append(f"| {label} | {result} | {duration} | {note} |")

    # --- 场景总览表 ---
    lines.extend(["", "## 场景评审总览", ""])
    release_by_id = {
        s.get("scenario_id", ""): s for s in (release_data.get("scenarios") or [])
    }
    scenario_ids = discover_scenario_ids(l3_dir, release_by_id)

    if scenario_ids:
        lines.append(
            "| 场景 | 预期分数 | 实际分数 | 校验 | 生效模板 | 模式 | MR | 备注 |"
        )
        lines.append("|------|----------|----------|------|----------|------|-----|------|")
        for sid in scenario_ids:
            art = scenario_artifacts(l3_dir, sid)
            row = release_by_id.get(sid)
            lines.append(
                render_scenario_summary_table_row(
                    art, release_row=row, record_dir=record_dir, scenario_id=sid
                )
            )
    else:
        lines.append("（无场景数据）")

    # --- 场景明细 ---
    if scenario_ids:
        lines.extend(["", "## 场景评审明细", ""])
        for sid in scenario_ids:
            art = scenario_artifacts(l3_dir, sid)
            lines.extend(
                render_scenario_detail_block(art, release_row=release_by_id.get(sid))
            )

    # --- S02 矩阵 ---
    matrix = release_data.get("matrix_summary")
    matrix_phase = phase_by_id(timing, "s02_matrix")
    matrix_dir = l3_dir / "S02_npe_optional_matrix"
    if matrix or matrix_phase:
        lines.extend(["", "## S02 提示词矩阵（P4）", ""])
        if matrix_phase:
            lines.append(
                f"- 阶段耗时：**{format_duration(matrix_phase.get('seconds'))}**"
            )
        if matrix:
            lines.extend(render_matrix_section(matrix, matrix_dir, include_details=True))

    # --- CI gate ---
    ci_phase = release_phases.get("ci_gate")
    if ci_phase:
        lines.extend(["", "## CI 门禁（P6）", ""])
        s02_review = read_json(l3_dir / "S02_npe_optional" / "review.json") or {}
        lines.extend(
            render_ci_gate_section(ci_phase, s02_review, threshold=DEFAULT_SCORE_THRESHOLD)
        )

    # --- S06 增量 ---
    incremental = release_data.get("incremental")
    s06_phase = phase_by_id(timing, "s06_incremental")
    if incremental or s06_phase or (l3_dir / "S06_incremental" / "review2.json").is_file():
        lines.extend(["", "## S06 增量评审（P7）", ""])
        if s06_phase:
            lines.append(
                f"- 阶段耗时：**{format_duration(s06_phase.get('seconds'))}**"
            )
        spec = load_scenario_index().get("S06_incremental", {})
        if spec:
            lines.append(
                f"- 预期分数：**{spec.get('expected_score_min', 0)}–"
                f"{spec.get('expected_score_max', 100)}**（±5）"
            )
        lines.extend(render_s06_section(l3_dir, incremental))

    phase_c = phase_by_id(timing, "phase_c")
    pc = release_phases.get("phase_c")
    if phase_c or pc:
        lines.extend(["", "## Phase C", ""])
        if phase_c:
            lines.append(
                f"- 阶段耗时：**{format_duration(phase_c.get('seconds'))}**"
            )
        if pc:
            lines.append(f"- 结果：**{'通过' if pc.get('ok') else '失败'}**")

    flaky = release_data.get("warnings") or []
    if flaky:
        lines.extend(["", "## 警告 / Flaky", ""])
        for w in flaky:
            lines.append(f"- {w}")

    lines.extend(
        [
            "",
            "## 运行环境",
            "",
            f"- 执行人：`{meta.get('user', '')}`",
            f"- 完成时间：`{summary.get('finished') or (timing or {}).get('finished') or ''}`",
            f"- Git commit：`{_git_head(record_dir.parent)}`",
            f"- 主机：`{meta.get('hostname', '')}`",
            "",
            "> 详细 JSON：`l3/<场景>/review.json`、`validate.json`；矩阵见 `l3/S02_npe_optional_matrix/`。",
            "> `test-results/` 已 gitignore；含 LLM 评审结论，请勿提交仓库。",
            "",
        ]
    )
    text = "\n".join(lines)
    (record_dir / "release.zh.md").write_text(text, encoding="utf-8")
    return text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--record-dir", required=True)
    parser.add_argument("--level", default="L3-full")
    parser.add_argument("--failed", action="store_true")
    args = parser.parse_args()
    write_release_md(Path(args.record_dir), level=args.level, failed=args.failed)
    print(f"Release report: {args.record_dir}/release.zh.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

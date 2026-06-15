#!/usr/bin/env python3
"""生成交付签收报告 release.zh.md（L3-full）。"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _read_json(path: Path) -> dict | list | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


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


def write_release_md(record_dir: Path, *, level: str, failed: bool) -> str:
    record_dir = Path(record_dir)
    meta = _read_json(record_dir / "meta.json") or {}
    summary = _read_json(record_dir / "summary.json") or {}
    l1 = _read_json(record_dir / "l1-smoke.json") or {}
    l2 = _read_json(record_dir / "l2-health.json") or {}
    release_data = _read_json(record_dir / "l3" / "release_data.json") or {}

    l1_ok = l1.get("failed", 1) == 0 if l1 else None
    l2_ok = l2.get("ok") if l2 else None

    lines = [
        "# L3-Full 交付签收报告",
        "",
        f"- 生成时间：`{datetime.now(timezone.utc).isoformat()}`",
        f"- 验收层级：**{level}**",
        f"- 报告目录：`{record_dir}`",
        f"- Git commit：`{_git_head(record_dir.parent)}`",
        f"- 主机：`{meta.get('hostname', '')}` / 用户 `{meta.get('user', '')}`",
        f"- **交付结论：{'不通过' if failed else '通过'}**",
        "",
        "## 门禁汇总",
        "",
        "| 阶段 | 结果 |",
        "|------|------|",
    ]
    if l1_ok is not None:
        lines.append(f"| L1 冒烟 | {'通过' if l1_ok else '失败'} ({l1.get('passed', 0)}/{l1.get('total', 0)}) |")
    if l2_ok is not None:
        lines.append(f"| L2 健康 | {'通过' if l2_ok else '失败'} |")

    phases = release_data.get("phases") or {}
    for key, label in (
        ("scenario_suite", "场景套件 S01–S05"),
        ("s02_matrix", "S02 三模板矩阵"),
        ("gitlab_publish", "GitLab 发帖"),
        ("ci_gate", "CI 门禁"),
        ("s06_incremental", "S06 增量评审"),
        ("phase_c", "Phase C 抽检"),
    ):
        if key in phases:
            lines.append(f"| {label} | {'通过' if phases[key].get('ok') else '失败'} |")

    lines.extend(["", "## 场景明细", ""])
    scenarios = release_data.get("scenarios") or []
    if scenarios:
        lines.append("| 场景 | 分数 | 校验 | MR | 备注 |")
        lines.append("|------|------|------|-----|------|")
        for s in scenarios:
            lines.append(
                f"| `{s.get('scenario_id', '')}` | {s.get('score', '')} | "
                f"{'通过' if s.get('validation_ok') else '失败'} | "
                f"{s.get('mr_url', '—')} | {s.get('note', '')} |"
            )
    else:
        lines.append("（无场景数据）")

    matrix = release_data.get("matrix_summary")
    if matrix:
        lines.extend(["", "## S02 矩阵", ""])
        lines.append(f"- 通过：{matrix.get('passed', 0)}/{matrix.get('passed', 0) + matrix.get('failed', 0)}")
        for r in matrix.get("results") or []:
            lines.append(
                f"- `{r.get('template_id')}`: score={r.get('score')} "
                f"issues={r.get('issue_count')} ok={r.get('ok')}"
            )

    incremental = release_data.get("incremental")
    if incremental:
        lines.extend(["", "## S06 增量", ""])
        lines.append(f"- 第一次 review：score={incremental.get('first_score')} sha={incremental.get('first_sha', '')[:12]}")
        lines.append(f"- 第二次 review（增量）：score={incremental.get('second_score')} ok={incremental.get('second_ok')}")

    flaky = release_data.get("warnings") or []
    if flaky:
        lines.extend(["", "## 警告 / Flaky", ""])
        for w in flaky:
            lines.append(f"- {w}")

    lines.extend([
        "",
        "## 签收",
        "",
        f"- 执行人：`{meta.get('user', '')}`",
        f"- 完成时间：`{summary.get('finished', '')}`",
        "",
        "> `test-results/` 已 gitignore；含 LLM 评审结论，请勿提交仓库。",
        "",
    ])
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

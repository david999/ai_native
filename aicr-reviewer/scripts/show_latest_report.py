#!/usr/bin/env python3
"""读取最新 test-results 目录，输出中文验收摘要（供 Agent / 人工快速查看）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_scripts = Path(__file__).resolve().parent
_repo = _scripts.parent.parent
_results = _repo / "test-results"


def _latest_dir() -> Path | None:
    if not _results.is_dir():
        return None
    dirs = [p for p in _results.iterdir() if p.is_dir() and p.name != ".gitkeep"]
    if not dirs:
        return None
    return max(dirs, key=lambda p: p.stat().st_mtime)


def main() -> int:
    latest = _latest_dir()
    if not latest:
        print("未找到 test-results 下的验收报告。请先运行 run_acceptance.ps1 -Level daily")
        return 1

    print(f"## 最新验收报告\n")
    print(f"- 目录：`{latest}`\n")

    for name, title in (
        ("summary.zh.md", "验收摘要"),
        ("l3.md", "L3 全链路"),
        ("l1-smoke.md", "L1 冒烟"),
        ("l2-health.md", "L2 健康"),
        ("summary.md", "英文摘要"),
    ):
        p = latest / name
        if p.is_file():
            print(f"### {title}\n")
            print(p.read_text(encoding="utf-8"))
            print()

    summary = latest / "summary.json"
    if summary.is_file():
        s = json.loads(summary.read_text(encoding="utf-8-sig"))
        print(f"**JSON 结论**：level={s.get('level')} failed={s.get('failed')}\n")

    l1 = latest / "l1-smoke.json"
    if l1.is_file():
        d = json.loads(l1.read_text(encoding="utf-8-sig"))
        print(f"**L1**：{d.get('passed')}/{d.get('total')} 通过（{d.get('title_zh', '')}）")

    l2 = latest / "l2-health.json"
    if l2.is_file():
        d = json.loads(l2.read_text(encoding="utf-8-sig"))
        ok = "通过" if d.get("ok") else "失败"
        print(f"**L2**：{ok}（{d.get('title_zh', '')}）")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

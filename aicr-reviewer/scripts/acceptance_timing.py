#!/usr/bin/env python3
"""验收阶段计时：timing.json 读写与报告格式化。"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def format_duration(seconds: int | float | None) -> str:
    if seconds is None:
        return "—"
    total = int(seconds)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m{secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h{minutes:02d}m"


def phase_result_label(phase: dict) -> str:
    if phase.get("skipped"):
        return "未执行"
    if phase.get("ok") is True:
        return "通过"
    if phase.get("ok") is False:
        return "失败"
    return "—"


class TimingRecorder:
    """记录验收各阶段耗时，写入 timing.json。"""

    def __init__(self) -> None:
        self.started = datetime.now(timezone.utc)
        self.phases: list[dict[str, Any]] = []
        self._current: dict[str, Any] | None = None
        self._t0: float | None = None

    def start(self, phase_id: str, label: str) -> None:
        self.end(ok=True)
        self._current = {"id": phase_id, "label": label}
        self._t0 = time.perf_counter()
        self._current["started"] = datetime.now(timezone.utc).isoformat()

    def end(
        self,
        *,
        ok: bool = True,
        skipped: bool = False,
        reason: str = "",
    ) -> None:
        if not self._current or self._t0 is None:
            return
        elapsed = int(time.perf_counter() - self._t0)
        entry = {
            **self._current,
            "ended": datetime.now(timezone.utc).isoformat(),
            "seconds": elapsed,
            "ok": ok,
        }
        if skipped:
            entry["skipped"] = True
            if reason:
                entry["reason"] = reason
        self.phases.append(entry)
        self._current = None
        self._t0 = None

    def add_skipped(self, phase_id: str, label: str, reason: str) -> None:
        self.phases.append(
            {
                "id": phase_id,
                "label": label,
                "skipped": True,
                "reason": reason,
                "seconds": None,
            }
        )

    def to_dict(self) -> dict[str, Any]:
        finished = datetime.now(timezone.utc)
        total = int((finished - self.started).total_seconds())
        return {
            "started": self.started.isoformat(),
            "finished": finished.isoformat(),
            "total_seconds": total,
            "phases": self.phases,
        }

    def write(self, path: Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def load_timing(record_dir: Path) -> dict | None:
    path = Path(record_dir) / "timing.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def phase_by_id(timing: dict | None, phase_id: str) -> dict | None:
    if not timing:
        return None
    for p in timing.get("phases") or []:
        if p.get("id") == phase_id:
            return p
    return None


def gate_phases_for_level(level: str) -> list[tuple[str, str]]:
    base = [
        ("L1", "L1 冒烟"),
        ("L2", "L2 健康"),
        ("l3_env_setup", "L3 环境（GitLab + Demo）"),
        ("scenario_suite", "场景套件 S01–S05"),
        ("s02_matrix", "S02 三模板矩阵"),
        ("gitlab_publish", "GitLab 发帖（S02）"),
        ("ci_gate", "CI 门禁"),
        ("s06_incremental", "S06 增量评审"),
        ("phase_c", "Phase C 抽检"),
    ]
    if level == "L3-standard":
        return base[:5]
    return base

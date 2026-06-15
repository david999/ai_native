#!/usr/bin/env python3
"""合并 L1/L2 与 L3 编排计时，写入 timing.json（Linux run_acceptance.sh 用）。"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from acceptance_timing import TimingRecorder, load_timing


def _read_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _l1_seconds(l1: dict) -> int:
    tests = l1.get("tests") or []
    if tests:
        return max(1, sum(int(t.get("ms") or 0) for t in tests) // 1000)
    return 0


def finalize(record_dir: Path, *, level: str, failed: bool) -> None:
    record_dir = Path(record_dir)
    existing = load_timing(record_dir)
    l3_phases = (existing or {}).get("phases") or []

    rec = TimingRecorder()
    if existing and existing.get("started"):
        rec.started = datetime.fromisoformat(existing["started"])
    elif (record_dir / "meta.json").is_file():
        meta = _read_json(record_dir / "meta.json") or {}
        if meta.get("started"):
            rec.started = datetime.fromisoformat(str(meta["started"]).replace("Z", "+00:00"))

    l1 = _read_json(record_dir / "l1-smoke.json")
    if l1 is not None:
        rec.phases.append(
            {
                "id": "L1",
                "label": "L1 冒烟",
                "seconds": _l1_seconds(l1),
                "ok": l1.get("failed", 1) == 0,
                "ended": datetime.now(timezone.utc).isoformat(),
            }
        )

    l2 = _read_json(record_dir / "l2-health.json")
    if l2 is not None:
        l2_timing = _read_json(record_dir / "l2-timing.json") or {}
        l2_sec = int(l2_timing.get("seconds") or 1)
        rec.phases.append(
            {
                "id": "L2",
                "label": "L2 健康",
                "seconds": max(1, l2_sec),
                "ok": bool(l2.get("ok")),
                "ended": datetime.now(timezone.utc).isoformat(),
            }
        )

    rec.phases.extend(l3_phases)
    rec.write(record_dir / "timing.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record-dir", required=True)
    ap.add_argument("--level", default="daily")
    ap.add_argument("--failed", action="store_true")
    args = ap.parse_args()
    finalize(Path(args.record_dir), level=args.level, failed=args.failed)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

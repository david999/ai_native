#!/usr/bin/env python3
"""Shell 侧验收进度（Linux run_acceptance.sh 的 L1/L2 等）。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from acceptance_timing import ProgressReporter, progress_plan_for_level


def _run_started(record_dir: Path) -> float | None:
    meta = record_dir / "meta.json"
    if not meta.is_file():
        return None
    data = json.loads(meta.read_text(encoding="utf-8-sig"))
    started = data.get("started")
    if not started:
        return None
    dt = datetime.fromisoformat(str(started).replace("Z", "+00:00"))
    return dt.timestamp()


def _elapsed_total(record_dir: Path) -> int:
    t0 = _run_started(record_dir)
    if t0 is None:
        return 0
    return max(0, int(datetime.now(timezone.utc).timestamp() - t0))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--record-dir", required=True)
    ap.add_argument("--level", required=True)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("plan")

    p_start = sub.add_parser("start")
    p_start.add_argument("phase_id")
    p_start.add_argument("label")

    p_end = sub.add_parser("end")
    p_end.add_argument("phase_id")
    p_end.add_argument("label")
    p_end.add_argument("--seconds", type=int, default=0)
    g = p_end.add_mutually_exclusive_group()
    g.add_argument("--ok", action="store_true")
    g.add_argument("--fail", action="store_true")
    g.add_argument("--skip", action="store_true")

    args = ap.parse_args()
    record_dir = Path(args.record_dir)
    reporter = ProgressReporter(args.level)
    if args.cmd == "plan":
        reporter.print_plan()
        return 0
    if args.cmd == "start":
        reporter._run_t0 = _run_started(record_dir) or reporter._run_t0  # noqa: SLF001
        reporter.start(args.phase_id, args.label)
        return 0
    ok = args.ok or (not args.fail and not args.skip)
    reporter._run_t0 = _run_started(record_dir) or reporter._run_t0  # noqa: SLF001
    reporter.end(
        args.phase_id,
        args.label,
        seconds=args.seconds,
        ok=ok,
        skipped=args.skip,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

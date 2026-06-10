#!/usr/bin/env python3
"""L2 健康检查：探测 /health 与 /health/detail，输出中文 JSON + Markdown 报告。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

_scripts = Path(__file__).resolve().parent
if str(_scripts) not in sys.path:
    sys.path.insert(0, str(_scripts))

from test_catalog import DETAIL_FIELD_ZH, HEALTH_CHECK_ZH, L2_REPORT_TITLE_ZH, status_zh
from report_zh import write_l2_health_md


def fetch_json(url: str, timeout: float = 10.0) -> tuple[int, dict | str]:
    req = Request(url, headers={"Accept": "application/json"})
    try:
        with urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return resp.status, json.loads(body)
    except URLError as e:
        return 0, str(e)


def _detail_zh(body: dict) -> list[dict]:
    rows = []
    for k, label in DETAIL_FIELD_ZH.items():
        if k not in body:
            continue
        v = body[k]
        if isinstance(v, bool):
            v_zh = "是" if v else "否"
        else:
            v_zh = str(v)
        rows.append({"field": k, "label_zh": label, "value": body[k], "value_zh": v_zh})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="AICR health check")
    parser.add_argument("--base-url", default="http://localhost:8001")
    parser.add_argument("--report-json", metavar="PATH", help="Write report JSON")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    report = {
        "title_zh": L2_REPORT_TITLE_ZH,
        "level": "L2",
        "description_zh": "本地 API 进程健康检查：确认 uvicorn 已启动且 evn/.env 配置已加载",
        "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "base_url": base,
        "checks": [],
        "ok": True,
    }

    for path in ("/health", "/health/detail"):
        status, data = fetch_json(f"{base}{path}")
        meta = HEALTH_CHECK_ZH.get(path, {})
        entry = {
            "path": path,
            "name_zh": meta.get("name_zh", path),
            "description_zh": meta.get("description_zh", ""),
            "http_status": status,
            "body": data,
        }
        if status != 200 or not isinstance(data, dict) or data.get("status") != "ok":
            report["ok"] = False
            entry["status"] = "failed"
            entry["status_zh"] = status_zh("failed")
        else:
            entry["status"] = "passed"
            entry["status_zh"] = status_zh("passed")
        if isinstance(data, dict) and path == "/health/detail":
            entry["detail_zh"] = _detail_zh(data)
        report["checks"].append(entry)

    if args.report_json:
        p = Path(args.report_json)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        write_l2_health_md(p)
        print(f"Report written to {args.report_json}")
        print(f"中文摘要: {p.with_suffix('.md')}")

    if report["ok"]:
        print(f"Health OK ({base})")
        return 0
    print(f"Health check FAILED ({base})", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

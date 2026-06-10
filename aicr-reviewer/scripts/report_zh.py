"""将 L1/L2 JSON 报告转为中文 Markdown 摘要。"""

from __future__ import annotations

import json
from pathlib import Path

from test_catalog import (
    DETAIL_FIELD_ZH,
    HEALTH_CHECK_ZH,
    L1_REPORT_TITLE_ZH,
    L2_REPORT_TITLE_ZH,
    smoke_entry_zh,
    status_zh,
)


def write_l1_smoke_md(json_path: Path, md_path: Path | None = None) -> str:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    md_path = md_path or json_path.with_suffix(".md")
    lines = [
        f"# {L1_REPORT_TITLE_ZH}",
        "",
        f"- 运行 ID：`{data.get('run_id', '')}`",
        f"- 层级：**L1（冒烟 / 单元）**",
        f"- 说明：无需 GitLab、无需 LLM，验证核心逻辑与 API 契约",
        f"- 合计：**{data.get('passed', 0)}** 通过 / **{data.get('failed', 0)}** 失败 / 共 **{data.get('total', 0)}** 项",
        "",
        "## 用例明细",
        "",
        "| 分类 | 用例 | 中文说明 | 结果 | 耗时(ms) |",
        "|------|------|----------|------|----------|",
    ]
    for t in data.get("tests", []):
        zh = smoke_entry_zh(t["name"])
        err = f" — {t.get('error', '')}" if t.get("error") else ""
        lines.append(
            f"| {zh['category_zh']} | `{t['name']}` | {zh['description_zh']} | "
            f"{status_zh(t['status'])}{err} | {t.get('ms', '')} |"
        )
    text = "\n".join(lines) + "\n"
    md_path.write_text(text, encoding="utf-8")
    return text


def write_l2_health_md(json_path: Path, md_path: Path | None = None) -> str:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    md_path = md_path or json_path.with_suffix(".md")
    ok = data.get("ok", False)
    lines = [
        f"# {L2_REPORT_TITLE_ZH}",
        "",
        f"- 运行 ID：`{data.get('run_id', '')}`",
        f"- 层级：**L2（本地 API 进程）**",
        f"- 服务地址：`{data.get('base_url', '')}`",
        f"- 总结果：**{'通过' if ok else '失败'}**",
        "",
        "## 检查项",
        "",
    ]
    for c in data.get("checks", []):
        path = c.get("path", "")
        meta = HEALTH_CHECK_ZH.get(path, {})
        lines.append(f"### {meta.get('name_zh', path)}")
        lines.append("")
        lines.append(f"- 路径：`{path}`")
        lines.append(f"- 说明：{meta.get('description_zh', '')}")
        lines.append(f"- HTTP：{c.get('http_status', '')}")
        lines.append(f"- 结果：**{status_zh(c.get('status', ''))}**")
        body = c.get("body")
        if isinstance(body, dict) and path == "/health/detail":
            lines.append("")
            lines.append("| 配置项 | 值 |")
            lines.append("|--------|-----|")
            for k, label in DETAIL_FIELD_ZH.items():
                if k in body:
                    v = body[k]
                    if isinstance(v, bool):
                        v = "是" if v else "否"
                    lines.append(f"| {label} | {v} |")
        lines.append("")
    text = "\n".join(lines) + "\n"
    md_path.write_text(text, encoding="utf-8")
    return text


def write_acceptance_summary_zh(record_dir: Path, *, level: str, failed: bool) -> None:
    lines = [
        "# 验收摘要（中文）",
        "",
        f"- 验收层级：**{level}**",
        f"- 报告目录：`{record_dir}`",
        f"- 总体结果：**{'失败' if failed else '通过'}**",
        "",
        "## 报告文件",
        "",
        "| 文件 | 说明 |",
        "|------|------|",
        "| `l1-smoke.md` | L1 冒烟用例中文明细 |",
        "| `l2-health.md` | L2 健康检查中文说明 |",
        "| `l3/` | L3 全链路（需 GitLab + LLM） |",
        "",
        "## 日常自动化（Agent）",
        "",
        "默认执行 `-Level daily`（L1+L2），不依赖 Docker。",
        "L3 需本地 GitLab 与 LLM 已启动后手动或显式 `-Level L3`。",
        "",
    ]
    (record_dir / "summary.zh.md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--record-dir", required=True)
    ap.add_argument("--level", default="daily")
    ap.add_argument("--failed", action="store_true")
    args = ap.parse_args()
    write_acceptance_summary_zh(Path(args.record_dir), level=args.level, failed=args.failed)

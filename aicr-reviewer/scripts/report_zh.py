"""将 L1/L2/L3 JSON 报告转为中文 Markdown 摘要。"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

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


def _read_json(path: Path) -> dict | list | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _scenario_changed_files(scenario_id: str) -> list[str]:
    if not scenario_id:
        return []
    repo_root = Path(__file__).resolve().parents[2]
    manifest = (
        repo_root / "test_data" / "fixtures" / "scenarios" / scenario_id / "manifest.yaml"
    )
    if not manifest.is_file():
        return []
    with open(manifest, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return [item["dest"] for item in data.get("files", []) if item.get("dest")]


def _collect_l3_matrix_summaries(l3_dir: Path) -> list[tuple[Path, dict]]:
    rows: list[tuple[Path, dict]] = []
    for matrix_dir in sorted(l3_dir.iterdir()):
        if not matrix_dir.is_dir():
            continue
        summary_path = matrix_dir / "matrix_summary.json"
        if not summary_path.is_file():
            continue
        summary = _read_json(summary_path) or {}
        rows.append((matrix_dir, summary))
    return rows


def write_l3_md(record_dir: Path, md_path: Path | None = None) -> str | None:
    l3_dir = record_dir / "l3"
    if not l3_dir.is_dir():
        return None

    md_path = md_path or (record_dir / "l3.md")
    apply_data = _read_json(l3_dir / "apply.json") or {}
    mr_data = _read_json(l3_dir / "mr.json") or {}

    scenarios = apply_data.get("scenarios") or []
    scenario_info = scenarios[0] if scenarios else {}
    scenario_id = scenario_info.get("scenario_id", "")
    changed_files = scenario_info.get("files") or _scenario_changed_files(scenario_id)

    lines = [
        "# L3 全链路验收（中文）",
        "",
        f"- 报告目录：`{record_dir}`",
        "",
        "## 场景与 MR",
        "",
        f"- 场景 ID：**{scenario_id}**",
        f"- 分支：`{scenario_info.get('branch', '')}`",
        f"- 提交：`{scenario_info.get('commit_sha', scenario_info.get('head_sha', ''))}`",
        f"- 变更文件：{', '.join(f'`{p}`' for p in changed_files) if changed_files else '—'}",
        f"- 项目 ID：`{mr_data.get('project_id', '')}`",
        f"- MR IID：`{mr_data.get('mr_iid', '')}`",
        f"- MR 链接：{mr_data.get('web_url', '—')}",
        f"- 源分支 → 目标：`{mr_data.get('source_branch', '')}` → `{mr_data.get('target_branch', '')}`",
        "",
    ]

    matrix_dirs = _collect_l3_matrix_summaries(l3_dir)
    if not matrix_dirs:
        lines.extend(["## 提示词矩阵", "", "未找到 matrix_summary.json。", ""])
        md_path.write_text("\n".join(lines), encoding="utf-8")
        return "\n".join(lines)

    total_pass = 0
    total_fail = 0
    for matrix_dir, summary in matrix_dirs:
        passed = summary.get("passed", 0)
        failed = summary.get("failed", 0)
        total_pass += passed
        total_fail += failed
        ok = summary.get("ok", failed == 0)
        lines.extend(
            [
                "## 提示词矩阵",
                "",
                f"- 场景目录：`{matrix_dir.name}`",
                f"- AICR：`{summary.get('base_url', 'http://localhost:8001')}`",
                f"- 矩阵结果：**{'通过' if ok else '失败'}**（{passed} 通过 / {failed} 失败）",
                "",
                "### 对比总览",
                "",
                "| 模板 | 说明 | 结果 | HTTP | 分数 | 完成 | Issue 数 | prompt_sha256 | 失败原因 |",
                "|------|------|------|------|------|------|----------|---------------|----------|",
            ]
        )
        for r in summary.get("results") or []:
            result_zh = "通过" if r.get("ok") else "失败"
            sha = (r.get("prompt_sha256") or "")[:12]
            fail = (r.get("failure_reason") or r.get("error") or "").replace("|", "/")[:60]
            desc = (r.get("template_description") or "").replace("|", "/")
            lines.append(
                f"| `{r.get('template_id', '')}` | {desc} | {result_zh} | "
                f"{r.get('http_status', '')} | {r.get('score', '')} | "
                f"{'是' if r.get('review_completed') else '否'} | "
                f"{r.get('issue_count', 0)} | {sha} | {fail} |"
            )

        lines.extend(["", "### 各模板详情", ""])
        for r in summary.get("results") or []:
            tid = r.get("template_id", "")
            lines.append(f"#### `{tid}`")
            lines.append("")
            if r.get("template_description"):
                lines.append(f"- 说明：{r['template_description']}")
            lines.append(f"- 结果：**{'通过' if r.get('ok') else '失败'}**")
            if r.get("error"):
                lines.append(f"- 错误：`{r['error']}`")
            if r.get("failure_reason") and r.get("failure_reason") != r.get("error"):
                lines.append(f"- 原因：{r['failure_reason']}")
            lines.append(f"- 分数：**{r.get('score', '—')}**")
            lines.append(f"- review_completed：{'是' if r.get('review_completed') else '否'}")
            lines.append(f"- 实际模板：`{r.get('system_template', '—')}`")
            if r.get("prompt_sha256"):
                lines.append(f"- prompt_sha256：`{r['prompt_sha256']}`")
            if r.get("summary"):
                lines.append(f"- 评审摘要：{r['summary']}")
            preview = r.get("issue_preview") or []
            if preview:
                lines.append("- Issue 预览：")
                for item in preview:
                    sev = item.get("severity", "")
                    loc = item.get("file", "")
                    line_no = item.get("line", "")
                    msg = item.get("message", "")
                    lines.append(f"  - [{sev}] `{loc}`:{line_no} — {msg}")
            else:
                detail_path = matrix_dir / f"{tid}.json"
                detail = _read_json(detail_path) or {}
                issues = detail.get("issues") or []
                if issues:
                    lines.append("- Issue 预览：")
                    for item in issues[:5]:
                        if not isinstance(item, dict):
                            continue
                        sev = item.get("severity", "")
                        loc = item.get("file", item.get("path", ""))
                        line_no = item.get("line", "")
                        msg = (item.get("message") or item.get("title") or "")[:200]
                        lines.append(f"  - [{sev}] `{loc}`:{line_no} — {msg}")
            lines.append("")

    lines.extend(
        [
            "## 矩阵汇总",
            "",
            f"- 模板合计：**{total_pass + total_fail}** 个",
            f"- 通过：**{total_pass}** / 失败：**{total_fail}**",
            "",
            "原始 JSON：`l3/<场景>/matrix_summary.json`、各 `system_spring_*.json`",
            "",
            "> `test-results/` 已在 `.gitignore` 中；报告可能含代码评审结论，请勿提交到 Git。",
            "",
        ]
    )
    text = "\n".join(lines)
    md_path.write_text(text, encoding="utf-8")
    return text


def write_acceptance_summary_zh(record_dir: Path, *, level: str, failed: bool) -> None:
    l3_summary_lines: list[str] = []
    l3_dir = record_dir / "l3"
    if l3_dir.is_dir():
        matrix_rows = _collect_l3_matrix_summaries(l3_dir)
        if matrix_rows:
            total_pass = sum(s.get("passed", 0) for _, s in matrix_rows)
            total_fail = sum(s.get("failed", 0) for _, s in matrix_rows)
            all_ok = all(s.get("ok", s.get("failed", 1) == 0) for _, s in matrix_rows)
            line = (
                f"- L3 矩阵：**{'通过' if all_ok else '失败'}** "
                f"（{total_pass}/{total_pass + total_fail} 模板"
            )
            if len(matrix_rows) > 1:
                line += f"，{len(matrix_rows)} 个场景"
            line += "）"
            mr_path = l3_dir / "mr.json"
            if mr_path.is_file():
                mr = json.loads(mr_path.read_text(encoding="utf-8-sig"))
                line += f"，MR !{mr.get('mr_iid', '')} — {mr.get('web_url', '')}"
            l3_summary_lines.append(line)
            for matrix_dir, summary in matrix_rows:
                ok = summary.get("ok", summary.get("failed", 1) == 0)
                l3_summary_lines.append(
                    f"  - `{matrix_dir.name}`：{'通过' if ok else '失败'} "
                    f"（{summary.get('passed', 0)}/{summary.get('passed', 0) + summary.get('failed', 0)}）"
                )

    lines = [
        "# 验收摘要（中文）",
        "",
        f"- 验收层级：**{level}**",
        f"- 报告目录：`{record_dir}`",
        f"- 总体结果：**{'失败' if failed else '通过'}**",
        "",
    ]
    if l3_summary_lines:
        lines.extend(l3_summary_lines)
        lines.append("")

    lines.extend(
        [
            "## 报告文件",
            "",
            "| 文件 | 说明 |",
            "|------|------|",
            "| `l1-smoke.md` | L1 冒烟用例中文明细 |",
            "| `l2-health.md` | L2 健康检查中文说明 |",
            "| `l3.md` | L3 场景、MR、多模板评审详情（中文） |",
            "| `l3/<场景>/comparison.md` | 模板对比表（英文表头） |",
            "",
            "`test-results/` 已 gitignore；含 LLM 评审结论时勿提交仓库。",
            "",
            "## 日常自动化（Agent）",
            "",
            "默认执行 `-Level daily`（L1+L2），不依赖 Docker。",
            "L3 需本地 GitLab、LLM 与 `REVIEW_API_ALLOW_INSECURE=1`（或配置 `REVIEW_API_SECRET`）。",
            "",
        ]
    )
    (record_dir / "summary.zh.md").write_text("\n".join(lines), encoding="utf-8")


def generate_all_reports(record_dir: Path, *, level: str, failed: bool) -> None:
    record_dir = Path(record_dir)
    l1 = record_dir / "l1-smoke.json"
    if l1.is_file():
        write_l1_smoke_md(l1)
    l2 = record_dir / "l2-health.json"
    if l2.is_file():
        write_l2_health_md(l2)
    write_l3_md(record_dir)
    write_acceptance_summary_zh(record_dir, level=level, failed=failed)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--record-dir", required=True)
    ap.add_argument("--level", default="daily")
    ap.add_argument("--failed", action="store_true")
    args = ap.parse_args()
    generate_all_reports(Path(args.record_dir), level=args.level, failed=args.failed)

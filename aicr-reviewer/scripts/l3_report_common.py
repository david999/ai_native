"""L3-full / L3 场景报告共用：读取 review/validate/manifest 并格式化为 Markdown。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_INDEX = REPO_ROOT / "test_data" / "fixtures" / "scenarios" / "manifest.yaml"
DEFAULT_TOLERANCE = 5.0
DEFAULT_SCORE_THRESHOLD = 60


def read_json(path: Path) -> dict | list | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8-sig"))


def md_table_cell(text: Any, *, max_len: int = 0) -> str:
    """Markdown 表格单元格：转义 | 与换行。"""
    s = str(text if text is not None else "").replace("|", "/").replace("\n", " ")
    if max_len > 0:
        s = s[:max_len]
    return s


def load_scenario_index() -> dict[str, dict]:
    if not SCENARIO_INDEX.is_file():
        return {}
    with open(SCENARIO_INDEX, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {s["id"]: s for s in data.get("scenarios", [])}


def mr_link(mr_url: str, mr_iid: int | str | None) -> str:
    if not mr_url:
        return "—"
    label = f"!{mr_iid}" if mr_iid else "MR"
    return f"[{label}]({mr_url})"


def infer_review_mode(review: dict) -> str:
    summary = str(review.get("summary") or "")
    if "No new commits since last successful review" in summary:
        return "skipped"
    if "Incremental review since" in summary:
        return "incremental"
    return "full"


def format_issue_preview(issues: list, limit: int = 5) -> list[str]:
    lines: list[str] = []
    for item in issues[:limit]:
        if not isinstance(item, dict):
            continue
        sev = item.get("severity", "?")
        loc = item.get("file") or item.get("path") or "?"
        line_no = item.get("line", "?")
        msg = md_table_cell(item.get("message") or item.get("title") or "", max_len=200)
        lines.append(f"  - [{sev}] `{loc}`:{line_no} — {msg}")
    return lines


def _apply_row_for_scenario(apply: dict, scenario_id: str) -> dict:
    rows = apply.get("scenarios") or []
    for row in rows:
        if row.get("scenario_id") == scenario_id:
            return row
    return rows[0] if rows else {}


def load_l3_root_context(l3_dir: Path) -> tuple[dict, dict, dict]:
    """L3 单场景：apply.json / mr.json 在 l3 根目录。"""
    apply = read_json(l3_dir / "apply.json") or {}
    mr = read_json(l3_dir / "mr.json") or {}
    row = _apply_row_for_scenario(apply, "")
    return apply, mr if isinstance(mr, dict) else {}, row


def discover_scenario_ids(l3_dir: Path, release_by_id: dict | None = None) -> list[str]:
    """含 review.json 的场景，或 L3 单场景根 apply.json。"""
    ids = collect_scenario_dirs(l3_dir)
    if ids:
        return ids
    apply = read_json(l3_dir / "apply.json") or {}
    rows = apply.get("scenarios") or []
    if rows:
        sid = rows[0].get("scenario_id", "")
        return [sid] if sid else []
    if release_by_id:
        return sorted(release_by_id.keys())
    return []


def scenario_artifacts(l3_dir: Path, scenario_id: str) -> dict[str, Any]:
    scen_dir = l3_dir / scenario_id
    review = read_json(scen_dir / "review.json") or {}
    validate = read_json(scen_dir / "validate.json") or {}
    mr = read_json(scen_dir / "mr.json") or {}
    apply = read_json(scen_dir / "apply.json") or {}
    apply_row = _apply_row_for_scenario(apply, scenario_id) if apply else {}

    # L3 单场景：根目录 apply/mr，矩阵在 l3/<scenario_id>/
    if not review and not mr and not apply_row:
        root_apply, root_mr, root_row = load_l3_root_context(l3_dir)
        if root_row.get("scenario_id", scenario_id) == scenario_id or (
            not root_row.get("scenario_id") and root_apply
        ):
            apply = root_apply
            apply_row = _apply_row_for_scenario(root_apply, scenario_id) or root_row
            mr = root_mr

    matrix_summary = read_json(scen_dir / "matrix_summary.json") or {}

    spec = load_scenario_index().get(scenario_id, {})
    checks = validate.get("checks") or {} if isinstance(validate, dict) else {}

    score = review.get("score")
    review_mode = infer_review_mode(review) if review else ""
    if not review and matrix_summary:
        review_mode = "matrix"
        results = matrix_summary.get("results") or []
        scores = [r.get("score") for r in results if r.get("score") is not None]
        if scores:
            score = f"{min(scores)}–{max(scores)}（{len(results)} 模板）"

    keywords_required = checks.get("keywords_required") or spec.get("must_find_keywords") or []
    keywords_missing = checks.get("keywords_missing") or []

    return {
        "scenario_id": scenario_id,
        "title": spec.get("title", ""),
        "spec": spec,
        "review": review,
        "validate": validate if isinstance(validate, dict) else {},
        "mr": mr if isinstance(mr, dict) else {},
        "apply": apply_row,
        "branch": apply_row.get("branch") or spec.get("branch", ""),
        "commit_sha": apply_row.get("commit_sha", ""),
        "score": score,
        "score_range": checks.get("score_range"),
        "expected_min": spec.get("expected_score_min"),
        "expected_max": spec.get("expected_score_max"),
        "validation_ok": validate.get("ok") if isinstance(validate, dict) else None,
        "keywords_required": keywords_required,
        "keywords_missing": keywords_missing,
        "file_hit": checks.get("file_hit"),
        "review_completed": review.get("review_completed") if review else None,
        "system_template_requested": review.get("system_template_requested", ""),
        "system_template": review.get("system_template", ""),
        "prompt_sha256": review.get("prompt_sha256", ""),
        "review_mode": review_mode or "full",
        "issues": review.get("issues") or [],
        "matrix_summary": matrix_summary if isinstance(matrix_summary, dict) else {},
    }


def score_expectation_label(art: dict, *, tolerance: float = DEFAULT_TOLERANCE) -> str:
    emin = art.get("expected_min")
    emax = art.get("expected_max")
    if emin is None or emax is None:
        return "—"
    return f"{emin}–{emax}（±{tolerance:g}）"


def score_in_range(art: dict) -> bool | None:
    validate = art.get("validate") or {}
    warnings = validate.get("warnings") or []
    for w in warnings:
        if "score" in str(w) and "outside" in str(w):
            return None  # relax_score 警告
    if validate.get("ok") is True:
        for err in validate.get("errors") or []:
            if "score" in str(err) and "outside" in str(err):
                return False
        return True
    for err in validate.get("errors") or []:
        if "score" in str(err) and "outside" in str(err):
            return False
    if validate.get("ok") is False:
        return False
    return True


def render_scenario_detail_block(art: dict, *, release_row: dict | None = None) -> list[str]:
    """单个场景 Markdown 块（#### 标题 + bullet 列表）。"""
    sid = art["scenario_id"]
    title = art.get("title") or sid
    lines = [f"#### `{sid}` — {title}", ""]

    if release_row:
        lines.append(f"- MR：{mr_link(release_row.get('mr_url', ''), release_row.get('mr_iid'))}")
    elif art.get("mr"):
        mr = art["mr"]
        lines.append(f"- MR：{mr_link(mr.get('web_url', ''), mr.get('mr_iid'))}")

    if art.get("branch"):
        lines.append(f"- 分支：`{art['branch']}`")
    if art.get("commit_sha"):
        lines.append(f"- 提交：`{str(art['commit_sha'])[:12]}`")

    expect = score_expectation_label(art)
    actual = art.get("score", "—")
    in_range = score_in_range(art)
    range_note = ""
    if in_range is False:
        range_note = " **（越界）**"
    elif in_range is None:
        range_note = " **（relax_score 警告）**"
    lines.append(f"- 预期分数：{expect}")
    lines.append(f"- 实际分数：**{actual}**{range_note}")

    val_ok = art.get("validation_ok")
    if release_row and release_row.get("validation_ok") is not None:
        val_ok = release_row.get("validation_ok")
    lines.append(f"- 校验：**{'通过' if val_ok else '失败' if val_ok is False else '—'}**")
    rc = art.get("review_completed")
    lines.append(
        f"- review_completed：{'是' if rc else '否' if rc is False else '—'}"
    )

    kw_req = art.get("keywords_required") or []
    if kw_req:
        missing = art.get("keywords_missing") or []
        hit = [k for k in kw_req if k not in missing]
        lines.append(f"- 关键词：命中 {hit or '—'}；缺失 {missing or '—'}")
    if art.get("file_hit") is not None:
        lines.append(f"- file_hit：**{'是' if art['file_hit'] else '否'}**")

    req_tpl = art.get("system_template_requested") or "—"
    applied_tpl = art.get("system_template") or "—"
    if art.get("review_mode") == "matrix" and not art.get("system_template"):
        applied_tpl = "（见下方矩阵，多模板）"
    lines.append(f"- 请求模板：`{md_table_cell(req_tpl)}`")
    lines.append(f"- 生效模板：`{md_table_cell(applied_tpl)}`")
    if art.get("prompt_sha256"):
        lines.append(f"- prompt_sha256：`{art['prompt_sha256']}`")
    lines.append(f"- 评审模式：**{art.get('review_mode', 'full')}**")

    issue_lines = format_issue_preview(art.get("issues") or [])
    if issue_lines:
        lines.append("- Issue 摘要：")
        lines.extend(issue_lines)
    elif art.get("review", {}).get("summary"):
        summary = md_table_cell(art["review"]["summary"], max_len=300)
        lines.append(f"- 评审摘要：{summary}")

    validate = art.get("validate") or {}
    for w in validate.get("warnings") or []:
        lines.append(f"- 校验警告：{w}")
    errors = validate.get("errors") or []
    if errors:
        lines.append("- 校验错误：")
        for e in errors:
            lines.append(f"  - {e}")

    lines.append("")
    return lines


def render_scenario_summary_table_row(
    art: dict,
    *,
    release_row: dict | None = None,
    record_dir: Path | None = None,
    scenario_id: str = "",
) -> str:
    sid = art.get("scenario_id") or scenario_id
    expect = md_table_cell(score_expectation_label(art))
    actual = art.get("score", "")
    in_range = score_in_range(art)
    score_cell = md_table_cell(actual)
    if in_range is False:
        score_cell = f"**{score_cell}** ⚠"
    elif in_range is None:
        score_cell = f"**{score_cell}**（relax）"

    val_ok = art.get("validation_ok")
    if release_row:
        val_ok = release_row.get("validation_ok", val_ok)
    val_label = "通过" if val_ok else "失败" if val_ok is False else "—"

    mr_url = ""
    mr_iid = None
    if release_row:
        mr_url = release_row.get("mr_url", "")
        mr_iid = release_row.get("mr_iid")
    elif art.get("mr"):
        mr_url = art["mr"].get("web_url", "")
        mr_iid = art["mr"].get("mr_iid")

    tpl = art.get("system_template") or art.get("system_template_requested") or "—"
    if art.get("review_mode") == "matrix" and tpl == "—":
        tpl = "矩阵多模板"
    mode = art.get("review_mode", "full")

    reason = ""
    if record_dir and sid:
        validate = read_json(record_dir / "l3" / sid / "validate.json")
        if isinstance(validate, dict):
            errs = validate.get("errors") or []
            if errs:
                reason = "; ".join(str(e) for e in errs[:2])
            warns = validate.get("warnings") or []
            if warns and not reason:
                reason = "; ".join(str(w) for w in warns[:1])
    if release_row and release_row.get("publish_ok") is False:
        reason = reason or "GitLab 发帖未通过"

    return (
        f"| `{sid}` | {expect} | {score_cell} | {val_label} | "
        f"`{md_table_cell(tpl)}` | {mode} | "
        f"{mr_link(mr_url, mr_iid)} | {md_table_cell(reason) or '—'} |"
    )


def collect_scenario_dirs(l3_dir: Path) -> list[str]:
    """返回含 review.json 的场景目录名（排除 matrix 目录）。"""
    ids: list[str] = []
    if not l3_dir.is_dir():
        return ids
    for child in sorted(l3_dir.iterdir()):
        if not child.is_dir():
            continue
        if child.name.endswith("_matrix"):
            continue
        if (child / "review.json").is_file():
            ids.append(child.name)
    return ids


def render_matrix_section(
    matrix: dict,
    matrix_dir: Path | None = None,
    *,
    include_details: bool = True,
) -> list[str]:
    lines: list[str] = []
    if not matrix:
        return lines

    passed = matrix.get("passed", 0)
    failed_n = matrix.get("failed", 0)
    lines.append(f"- 通过：**{passed}/{passed + failed_n}**")
    lines.append("")
    lines.append(
        "| 模板 | 说明 | 分数 | issues | 结果 | 生效模板 | prompt_sha256 |"
    )
    lines.append("|------|------|------|--------|------|----------|---------------|")
    for r in matrix.get("results") or []:
        desc = md_table_cell(r.get("template_description") or "", max_len=40)
        sha = md_table_cell(r.get("prompt_sha256") or "")
        tpl = md_table_cell(r.get("system_template") or "—")
        lines.append(
            f"| `{r.get('template_id', '')}` | {desc} | {r.get('score', '')} | "
            f"{r.get('issue_count', len(r.get('issues') or []))} | "
            f"{'通过' if r.get('ok') else '失败'} | "
            f"`{tpl}` | `{sha}` |"
        )

    if not include_details:
        lines.append("")
        return lines

    lines.extend(["", "### 各模板 Issue 预览", ""])
    for r in matrix.get("results") or []:
        tid = r.get("template_id", "")
        lines.append(f"#### `{tid}`")
        preview = r.get("issue_preview") or []
        if preview:
            for item in preview:
                sev = item.get("severity", "")
                loc = item.get("file", "")
                line_no = item.get("line", "")
                msg = md_table_cell(item.get("message") or "")
                lines.append(f"  - [{sev}] `{loc}`:{line_no} — {msg}")
        elif matrix_dir and matrix_dir.is_dir():
            detail = read_json(matrix_dir / f"{tid}.json") or {}
            for item in format_issue_preview(detail.get("issues") or [], limit=3):
                lines.append(item)
        lines.append("")

    return lines


def render_s06_section(l3_dir: Path, incremental: dict | None) -> list[str]:
    lines: list[str] = []
    s06_dir = l3_dir / "S06_incremental"
    r1 = read_json(s06_dir / "review1.json") or {}
    r2 = read_json(s06_dir / "review2.json") or {}
    v2 = read_json(s06_dir / "validate2.json") or {}

    if r1:
        lines.append("**第一次（全量 `--force-full`）**")
        lines.append(f"- 分数：**{r1.get('score', '—')}**")
        lines.append(f"- 模板：`{r1.get('system_template', '—')}`")
        if r1.get("prompt_sha256"):
            lines.append(f"- prompt_sha256：`{r1['prompt_sha256']}`")
        lines.append("")

    if r2:
        lines.append("**第二次（增量 `--no-force-full`）**")
        lines.append(f"- 分数：**{r2.get('score', '—')}**")
        lines.append(f"- 模板：`{r2.get('system_template', '—')}`")
        if r2.get("prompt_sha256"):
            lines.append(f"- prompt_sha256：`{r2['prompt_sha256']}`")
        lines.append(f"- 评审模式：**{infer_review_mode(r2)}**")
        if isinstance(v2, dict):
            lines.append(f"- validate2：**{'通过' if v2.get('ok') else '失败'}**")
            for err in v2.get("errors") or []:
                lines.append(f"  - {err}")
        issue_lines = format_issue_preview(r2.get("issues") or [], limit=5)
        if issue_lines:
            lines.append("- Issue 摘要：")
            lines.extend(issue_lines)
        lines.append("")

    if incremental and not r1 and not r2:
        lines.append(
            f"- 第一次 review：score={incremental.get('first_score')} "
            f"sha={(incremental.get('first_sha') or '')[:12]}"
        )
        lines.append(
            f"- 第二次 review（增量）：score={incremental.get('second_score')} "
            f"ok={incremental.get('second_ok')}"
        )

    return lines


def render_ci_gate_section(
    ci_phase: dict,
    s02_review: dict | None,
    *,
    threshold: float = DEFAULT_SCORE_THRESHOLD,
) -> list[str]:
    lines: list[str] = []
    if not ci_phase:
        return lines

    score = s02_review.get("score") if s02_review else None
    completed = s02_review.get("review_completed") if s02_review else None
    lines.append(f"- 结果：**{'通过' if ci_phase.get('ok') else '失败'}**")
    lines.append(f"- 预期 exit：**{ci_phase.get('expected_exit', 1)}**")
    lines.append(f"- 实际 exit：**{ci_phase.get('exit_code', '—')}**")
    if score is not None:
        lines.append(f"- S02 缓存分数：**{score}**（review_completed={completed}）")
    threshold = ci_phase.get("threshold") or threshold
    lines.append(f"- 门禁阈值：**{threshold}**（score < 阈值 → exit 1）")
    if ci_phase.get("cached"):
        lines.append("- 说明：基于 S02 baseline review.json 模拟 CI gate（非真实 Pipeline）")
    lines.append("")
    return lines

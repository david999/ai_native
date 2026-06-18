#!/usr/bin/env python3
"""L3b：通过 GitLab API 采集 MR Pipeline 的 review job 日志，生成结构化报告。"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_INDEX = REPO_ROOT / "test_data" / "fixtures" / "scenarios" / "manifest.yaml"
RESULTS_ROOT = REPO_ROOT / "test-results"

SCORE_RE = re.compile(r"Review completed\. Score:\s*([\d.]+)")
THRESHOLD_RE = re.compile(r"threshold\s*([\d.]+)", re.I)
ERROR_SCORE_RE = re.compile(
    r"ERROR:\s*score\s*([\d.]+)\s*<\s*threshold\s*([\d.]+)", re.I
)
# 与 run_review.py 输出对齐；勿用裸 "WARNING:"（pip/apk 等噪声会误判 fail-open）
FAIL_OPEN_SUBSTRINGS = (
    "Review skipped (fail-open)",
    "Reviewer timed out after",
    "Reviewer unreachable:",
    "Reviewer unavailable: HTTP",
    "Reviewer returned HTTP error:",
    "Reviewer request failed:",
)


def load_dotenv() -> None:
    aicr = REPO_ROOT / "aicr-reviewer"
    if str(aicr) not in sys.path:
        sys.path.insert(0, str(aicr))
    from app.env_loader import apply_monorepo_env

    apply_monorepo_env()


def api_get(url: str, token: str) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={"PRIVATE-TOKEN": token},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_scenario_spec(scenario_id: str) -> dict:
    if not SCENARIO_INDEX.is_file() or not scenario_id:
        return {}
    with open(SCENARIO_INDEX, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    for s in data.get("scenarios", []):
        if s.get("id") == scenario_id:
            return s
    return {}


def parse_job_log(log_text: str) -> dict:
    score = None
    threshold = None
    blocked = False
    fail_open = False
    fail_open_reason = ""

    m = SCORE_RE.search(log_text)
    if m:
        score = float(m.group(1))

    em = ERROR_SCORE_RE.search(log_text)
    if em:
        score = float(em.group(1))
        threshold = float(em.group(2).rstrip("."))
        blocked = True

    tm = THRESHOLD_RE.search(log_text)
    if tm and threshold is None:
        threshold = float(tm.group(1))

    for sub in FAIL_OPEN_SUBSTRINGS:
        if sub not in log_text:
            continue
        fail_open = True
        for line in log_text.splitlines():
            if sub in line:
                fail_open_reason = line.strip()[:200]
                break
        if not fail_open_reason:
            fail_open_reason = sub
        break

    if "Review passed." in log_text and score is not None and threshold is not None:
        blocked = score < threshold
    if "Pipeline fails to block merge" in log_text:
        blocked = True

    return {
        "score": score,
        "threshold": threshold,
        "blocked": blocked,
        "fail_open": fail_open,
        "fail_open_reason": fail_open_reason,
        "passed": not blocked and not fail_open,
    }


def find_review_job(jobs: list) -> dict | None:
    for job in jobs:
        if job.get("name") == "review":
            return job
    return None


def collect_l3b(
    *,
    gitlab_url: str,
    token: str,
    project_id: int,
    mr_iid: int | None = None,
    pipeline_id: int | None = None,
    scenario_id: str = "",
) -> dict:
    base = gitlab_url.rstrip("/")
    mr: dict = {}
    if mr_iid is not None:
        mr = api_get(
            f"{base}/api/v4/projects/{project_id}/merge_requests/{mr_iid}",
            token,
        )

    if pipeline_id is None:
        if mr_iid is None:
            raise SystemExit("Provide --mr-iid or --pipeline-id")
        pipelines = api_get(
            f"{base}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/pipelines",
            token,
        )
        if not pipelines:
            raise SystemExit("No pipelines found for MR")
        pipeline_id = int(pipelines[0]["id"])

    pipeline = api_get(
        f"{base}/api/v4/projects/{project_id}/pipelines/{pipeline_id}",
        token,
    )
    jobs = api_get(
        f"{base}/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs",
        token,
    )
    review_job = find_review_job(jobs)
    if not review_job:
        raise SystemExit("No 'review' job in pipeline")

    job_id = int(review_job["id"])
    log_url = f"{base}/api/v4/projects/{project_id}/jobs/{job_id}/trace"
    req = urllib.request.Request(log_url, headers={"PRIVATE-TOKEN": token}, method="GET")
    with urllib.request.urlopen(req, timeout=120) as resp:
        job_log = resp.read().decode("utf-8", errors="replace")

    parsed = parse_job_log(job_log)
    spec = load_scenario_spec(scenario_id)
    job_status = review_job.get("status", "")

    web_url = mr.get("web_url") or ""
    pipeline_web = pipeline.get("web_url") or f"{base}/-/pipelines/{pipeline_id}"
    job_web = review_job.get("web_url") or f"{base}/-/jobs/{job_id}"

    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "scenario_id": scenario_id,
        "scenario_spec": {
            "expected_score_min": spec.get("expected_score_min"),
            "expected_score_max": spec.get("expected_score_max"),
            "title": spec.get("title", ""),
        },
        "project_id": project_id,
        "mr_iid": mr_iid or mr.get("iid"),
        "mr_url": web_url,
        "source_branch": mr.get("source_branch", ""),
        "target_branch": mr.get("target_branch", ""),
        "pipeline_id": pipeline_id,
        "pipeline_url": pipeline_web,
        "pipeline_status": pipeline.get("status", ""),
        "review_job_id": job_id,
        "review_job_url": job_web,
        "review_job_status": job_status,
        "template_note": "CI 未传 system_template → 自动选择 system_spring.j2（Java/Spring）",
        "score_threshold_ci": parsed.get("threshold") or float(
            os.environ.get("AICR_SCORE_THRESHOLD", "60")
        ),
        "parsed": parsed,
        "job_log": job_log,
    }


def write_l3b_report_md(data: dict, out_dir: Path) -> str:
    parsed = data.get("parsed") or {}
    spec = data.get("scenario_spec") or {}
    score = parsed.get("score")
    threshold = parsed.get("threshold") or data.get("score_threshold_ci")
    job_status = data.get("review_job_status", "")

    ci_pass = job_status == "success"
    if parsed.get("fail_open"):
        ci_result = "通过（fail-open）"
    elif parsed.get("blocked"):
        ci_result = "失败（低分拦截）"
    elif ci_pass:
        ci_result = "通过"
    else:
        ci_result = f"失败（job {job_status}）"

    expect_line = "—"
    if spec.get("expected_score_min") is not None:
        expect_line = f"{spec['expected_score_min']}–{spec['expected_score_max']}（验收区间，CI 阈值为 {threshold}）"

    mr_link = "—"
    if data.get("mr_url"):
        mr_link = f"[!{data.get('mr_iid')}]({data['mr_url']})"

    lines = [
        "# L3b Runner Pipeline 验收报告",
        "",
        f"- 采集时间：`{data.get('collected_at', '')}`",
        f"- 场景：`{data.get('scenario_id') or '—'}`",
        f"- MR：{mr_link}",
        f"- 分支：`{data.get('source_branch', '')}` → `{data.get('target_branch', '')}`",
        f"- Pipeline：[#{data.get('pipeline_id')}]({data.get('pipeline_url', '')})（{data.get('pipeline_status', '')}）",
        f"- review job：[#{data.get('review_job_id')}]({data.get('review_job_url', '')})（**{job_status}**）",
        "",
        "## 评审结果",
        "",
        f"- CI job 结论：**{ci_result}**",
        f"- 解析分数：**{score if score is not None else '—'}**",
        f"- CI 门禁阈值：**{threshold}**",
        f"- 场景预期分数区间：{expect_line}",
        f"- fail-open：{'是' if parsed.get('fail_open') else '否'}",
    ]
    if parsed.get("fail_open_reason"):
        lines.append(f"- fail-open 原因：{parsed['fail_open_reason']}")
    lines.extend(
        [
            f"- 提示词模板：{data.get('template_note', '')}",
            "",
            "## 说明",
            "",
            "- L3b 验证 GitLab Runner → `run_review.py` → 宿主机 AICR 全链路。",
            "- 低分场景（如 S02）预期 job **failed**；fail-open（AICR 不可达/超时）预期 job **passed**。",
            "",
            "## 原始证据",
            "",
            f"- `pipeline.json` — Pipeline/Job 元数据",
            f"- `job_log.txt` — review job 完整日志",
            "",
        ]
    )
    text = "\n".join(lines)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "l3b_report.zh.md").write_text(text, encoding="utf-8")
    return text


def main() -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Collect L3b GitLab CI review job report")
    parser.add_argument("--project-id", type=int, required=True)
    parser.add_argument("--mr-iid", type=int, help="Merge request IID")
    parser.add_argument("--pipeline-id", type=int, help="Pipeline ID (overrides latest MR pipeline)")
    parser.add_argument("--scenario", default="", help="Scenario id e.g. S02_npe_optional for expected range")
    parser.add_argument(
        "--output-dir",
        help="Output directory (default: test-results/l3b-<timestamp>)",
    )
    args = parser.parse_args()

    gitlab_url = os.environ.get("GITLAB_URL", "http://localhost:8000")
    token = os.environ.get("AICR_BOT_TOKEN") or os.environ.get("ROOT_PAT", "")
    if not token:
        print("AICR_BOT_TOKEN or ROOT_PAT required", file=sys.stderr)
        return 1

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    out_dir = Path(args.output_dir) if args.output_dir else RESULTS_ROOT / f"l3b-{ts}"

    data = collect_l3b(
        gitlab_url=gitlab_url,
        token=token,
        project_id=args.project_id,
        mr_iid=args.mr_iid,
        pipeline_id=args.pipeline_id,
        scenario_id=args.scenario,
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    meta = {k: v for k, v in data.items() if k != "job_log"}
    (out_dir / "pipeline.json").write_text(
        json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "job_log.txt").write_text(data["job_log"], encoding="utf-8")
    write_l3b_report_md(data, out_dir)

    print(f"L3b report: {out_dir / 'l3b_report.zh.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

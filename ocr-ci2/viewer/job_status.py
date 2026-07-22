"""Gateway MR 评审任务状态：中文展示与说明（HTML / JSON API / SPA 共用）。"""

from __future__ import annotations

# 任务状态（非 issue 严重级别）：表示 Gateway 单次 MR 评审流水线是否跑通
JOB_STATUS_LABELS: dict[str, str] = {
    "success": "已完成",
    "failed": "失败",
    "running": "进行中",
    "queued": "排队中",
}

JOB_STATUS_HINTS: dict[str, str] = {
    "success": "Gateway 评审任务已执行完毕（ocr review 完成并写入索引，可查看评论）",
    "failed": "评审任务失败：拉取代码、ocr review 或回写 GitLab 等环节出错",
    "running": "评审任务正在执行（准备仓库或运行 ocr review）",
    "queued": "评审任务已入队，等待 Gateway  worker 执行",
}

# 工作台页脚简短说明（一行）
JOB_STATUS_LEGEND = (
    "任务状态：已完成=评审跑完并入库 · 失败=拉仓/ocr/发帖出错 · 进行中/排队=实时任务"
)


def job_status_label(status: str) -> str:
    """状态码 → 中文标签。"""
    return JOB_STATUS_LABELS.get(status or "", status or "—")


def job_status_hint(status: str) -> str:
    """状态码 → 悬停说明。"""
    return JOB_STATUS_HINTS.get(status or "", "")


def enrich_status_fields(row: dict) -> dict:
    """为列表行 dict 补充 status_label / status_hint（就地修改并返回）。"""
    status = row.get("status") or ""
    row["status_label"] = job_status_label(status)
    row["status_hint"] = job_status_hint(status)
    return row

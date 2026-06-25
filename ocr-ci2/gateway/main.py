"""OCR Gateway HTTP API — GitLab CI MR 流水线轻量触发层。

逻辑清单：
- 鉴权：X-OCR-Gateway-Token 须与 OCR_GATEWAY_SECRET 一致（未配置 secret 返回 503）
- POST /v1/review/merge-request：校验 project_id、异步入队、返回 202
- GET /v1/jobs/{id}：内存 job 状态查询
- 不做：POST 时等待 OCR 完成；跨重启持久化 job；启动时校验 ocr 二进制
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from gateway import config as gw_config
from gateway.review_service import (
    ReviewRequest,
    enqueue_review,
    get_job,
    queue_depth,
    workspace_mirror_count,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="OCR Gateway", version="0.1.0")


class MergeRequestReviewBody(BaseModel):
    project_id: str = Field(..., description="GitLab project id")
    project_path: str = Field(..., description="e.g. java_group/spring-cloud-demo")
    mr_iid: str = Field(..., description="MR internal id")
    target_branch: str = Field(..., description="MR target branch name")
    commit_sha: str = Field(..., description="Head commit SHA for --to")


class ReviewAcceptedResponse(BaseModel):
    job_id: str
    status: str
    message: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    message: str


def verify_gateway_token(
    x_ocr_gateway_token: Annotated[str | None, Header()] = None,
) -> None:
    """拒绝未配置 secret 或 token 错误的请求。

    不做：限流；记录 token 明文。
    """
    secret = gw_config.gateway_secret()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="OCR_GATEWAY_SECRET is not configured; refusing requests",
        )
    if x_ocr_gateway_token != secret:
        raise HTTPException(status_code=401, detail="invalid gateway token")


@app.get("/health")
def health() -> dict[str, str | int]:
    return {
        "status": "ok",
        "service": "ocr-gateway",
        "queue_depth": queue_depth(),
        "max_concurrent": gw_config.MAX_CONCURRENT,
        "workspace_mirrors": workspace_mirror_count(),
        "workspace_max_mirrors": gw_config.WORKSPACE_MAX_MIRRORS,
    }


@app.post(
    "/v1/review/merge-request",
    response_model=ReviewAcceptedResponse,
    status_code=202,
    dependencies=[Depends(verify_gateway_token)],
)
def trigger_mr_review(body: MergeRequestReviewBody) -> ReviewAcceptedResponse:
    """接受 MR 评审任务；在后台线程异步执行 OCR。

    不做：阻塞至评审结束；按 project_id+mr_iid 全局去重。
    """
    try:
        gw_config.validate_project_id(body.project_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    job_id = uuid.uuid4().hex[:12]
    req = ReviewRequest(
        project_id=body.project_id,
        project_path=body.project_path,
        mr_iid=body.mr_iid,
        target_branch=body.target_branch,
        commit_sha=body.commit_sha,
    )
    job = enqueue_review(job_id, req)
    logger.info(
        "queued mr review job_id=%s project=%s mr=%s",
        job_id,
        body.project_path,
        body.mr_iid,
    )
    return ReviewAcceptedResponse(
        job_id=job.job_id,
        status=job.status,
        message="review queued",
    )


@app.get(
    "/v1/jobs/{job_id}",
    response_model=JobStatusResponse,
    dependencies=[Depends(verify_gateway_token)],
)
def job_status(job_id: str) -> JobStatusResponse:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="job not found")
    return JobStatusResponse(job_id=job.job_id, status=job.status, message=job.message)

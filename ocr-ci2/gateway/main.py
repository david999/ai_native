"""OCR Gateway HTTP API + Dashboard UI on :8010."""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

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

app = FastAPI(title="OCR Gateway", version="0.2.0", docs_url="/docs", redoc_url=None)


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
    session_id: str = ""
    encoded_repo: str = ""


def verify_gateway_token(
    x_ocr_gateway_token: Annotated[str | None, Header()] = None,
) -> None:
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
        "dashboard": "enabled",
    }


@app.post(
    "/v1/review/merge-request",
    response_model=ReviewAcceptedResponse,
    status_code=202,
    dependencies=[Depends(verify_gateway_token)],
)
def trigger_mr_review(body: MergeRequestReviewBody) -> ReviewAcceptedResponse:
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
    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        message=job.message,
        session_id=job.session_id,
        encoded_repo=job.encoded_repo,
    )


# Dashboard 必须在 /health、/v1 之后挂载：SPA 的 StaticFiles("/") 否则会吞掉 API
from viewer.routes import mount_dashboard  # noqa: E402

mount_dashboard(app)

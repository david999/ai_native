import logging
from fastapi import APIRouter, BackgroundTasks, Request, HTTPException
from pydantic import BaseModel
from typing import List, Dict

from app.config import (
    AICR_BOT_TOKEN, GITLAB_WEBHOOK_SECRET, GITLAB_WEBHOOK_ALLOW_INSECURE,
    LLM_API_KEY, REVIEW_API_SECRET,
)
from app.exceptions import LLMReviewError, NoReviewableChangesError, ReviewError
from app.review.orchestrator import ReviewOrchestrator
from app.gitlab.context_builder import ContextBuilder
from app.llm.factory import create_llm_provider
from app.gitlab.publisher import GitLabPublisher

logger = logging.getLogger("aicr")
router = APIRouter()

FAIL_OPEN_SCORE = 100.0


class ReviewRequest(BaseModel):
    project_id: int
    mr_iid: int
    diff: str = ""


class ReviewResult(BaseModel):
    score: float
    issues: List[Dict]
    code_quality: List[Dict] = []
    summary: str = ""


def _fail_open_review(reason: str) -> ReviewResult:
    """评审服务异常时 fail-open：返回满分，让 CI/MR 通过。"""
    logger.error(f"Review fail-open (MR passes): {reason}")
    return ReviewResult(
        score=FAIL_OPEN_SCORE,
        issues=[],
        summary=f"Review skipped (fail-open): {reason}",
    )


def _verify_review_auth(request: Request) -> None:
    """校验 CI 密钥；未配置 REVIEW_API_SECRET 时跳过（便于本地开发）。"""
    if not REVIEW_API_SECRET:
        return
    token = request.headers.get("X-AICR-Secret", "")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if token != REVIEW_API_SECRET:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _run_orchestrator(project_id: int, mr_iid: int, extra_diff: str = "") -> dict:
    if not AICR_BOT_TOKEN:
        raise HTTPException(status_code=500, detail="AICR_BOT_TOKEN is not configured")

    try:
        llm = create_llm_provider()
    except ValueError as e:
        raise HTTPException(status_code=503, detail="LLM provider not configured") from e

    orchestrator = ReviewOrchestrator(
        context_builder=ContextBuilder(),
        llm_provider=llm,
        publisher=GitLabPublisher(),
    )
    return orchestrator.run(project_id=project_id, mr_iid=mr_iid, extra_diff=extra_diff)


@router.get("/health")
def health():
    from app.config import GITLAB_URL, LLM_PROVIDER, LLM_MODEL
    return {
        "status": "ok",
        "gitlab_url": GITLAB_URL,
        "token_set": bool(AICR_BOT_TOKEN),
        "llm_provider": LLM_PROVIDER,
        "llm_model": LLM_MODEL,
        "llm_key_set": bool(LLM_API_KEY),
        "review_auth_required": bool(REVIEW_API_SECRET),
    }


@router.post("/review", response_model=ReviewResult)
def review(req: ReviewRequest, request: Request):
    _verify_review_auth(request)

    try:
        result = _run_orchestrator(req.project_id, req.mr_iid, req.diff)
    except NoReviewableChangesError as e:
        logger.info(f"No reviewable changes: {e}")
        return ReviewResult(score=FAIL_OPEN_SCORE, issues=[], summary=str(e))
    except HTTPException as e:
        if e.status_code == 401:
            raise
        return _fail_open_review(str(e.detail))
    except (LLMReviewError, ReviewError) as e:
        return _fail_open_review(str(e))
    except Exception as e:
        logger.error(f"Unexpected review error: {e}", exc_info=True)
        return _fail_open_review(str(e))

    return ReviewResult(
        score=result["score"],
        issues=result["issues"],
        code_quality=result.get("code_quality", []),
        summary=result.get("summary", ""),
    )


@router.post("/webhook/gitlab")
async def gitlab_webhook(request: Request, background_tasks: BackgroundTasks):
    if not GITLAB_WEBHOOK_SECRET:
        if not GITLAB_WEBHOOK_ALLOW_INSECURE:
            raise HTTPException(
                status_code=503,
                detail="GITLAB_WEBHOOK_SECRET not configured",
            )
        logger.warning("Webhook running without secret (GITLAB_WEBHOOK_ALLOW_INSECURE=1)")
    else:
        token = request.headers.get("X-Gitlab-Token", "")
        if token != GITLAB_WEBHOOK_SECRET:
            logger.warning("Webhook token mismatch")
            raise HTTPException(status_code=401, detail="Unauthorized")

    body = await request.json()
    object_kind = body.get("object_kind", "")
    if object_kind != "merge_request":
        return {"status": "ignored", "reason": f"not merge_request: {object_kind}"}

    action = body.get("object_attributes", {}).get("action", "")
    if action not in ("open", "update", "reopen"):
        return {"status": "ignored", "reason": f"action: {action}"}

    project_id = body.get("project", {}).get("id")
    mr_iid = body.get("object_attributes", {}).get("iid")
    if not project_id or not mr_iid:
        return {"status": "ignored", "reason": "missing project_id or mr_iid"}

    def _run_review():
        try:
            _run_orchestrator(project_id, mr_iid)
        except Exception as e:
            logger.error(f"Webhook review failed: {e}", exc_info=True)

    background_tasks.add_task(_run_review)
    return {"status": "accepted", "project_id": project_id, "mr_iid": mr_iid}

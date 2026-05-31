import logging
import secrets
from fastapi import APIRouter, BackgroundTasks, Request, HTTPException
from pydantic import BaseModel
from typing import List, Dict

from app.config import (
    AICR_BOT_TOKEN,
    AICR_INCREMENTAL_REVIEW,
    GITLAB_WEBHOOK_SECRET,
    GITLAB_WEBHOOK_ALLOW_INSECURE,
    LLM_API_KEY,
    REVIEW_API_SECRET,
    REVIEW_API_ALLOW_INSECURE,
)
from app.api.concurrency import (
    acquire_review_slot,
    release_review_slot,
    ReviewCapacityError,
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
    force_full: bool = False


class ReviewResult(BaseModel):
    score: float
    issues: List[Dict]
    code_quality: List[Dict] = []
    summary: str = ""
    # True 表示 LLM 已完成评审；CI 仅在此为 true 且分数低于阈值时才失败
    review_completed: bool = False


def _fail_open_review(reason: str) -> ReviewResult:
    """评审未实际完成（异常/跳过）：返回占位分数，由 CI 脚本放行 MR。"""
    logger.error(f"Review fail-open (MR passes): {reason}")
    return ReviewResult(
        score=FAIL_OPEN_SCORE,
        issues=[],
        summary=f"Review skipped (fail-open): {reason}",
        review_completed=False,
    )


def _extract_review_token(request: Request) -> str:
    token = request.headers.get("X-AICR-Secret", "")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    return token


def _verify_review_auth(request: Request) -> None:
    """校验 CI 密钥；未配置 REVIEW_API_SECRET 时需显式 REVIEW_API_ALLOW_INSECURE=1。"""
    if not REVIEW_API_SECRET:
        if not REVIEW_API_ALLOW_INSECURE:
            raise HTTPException(
                status_code=503,
                detail="REVIEW_API_SECRET not configured",
            )
        logger.warning(
            "Review API running without secret (REVIEW_API_ALLOW_INSECURE=1)"
        )
        return

    token = _extract_review_token(request)
    if not token or not secrets.compare_digest(token, REVIEW_API_SECRET):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _run_orchestrator(
    project_id: int,
    mr_iid: int,
    extra_diff: str = "",
    *,
    force_full: bool = False,
) -> dict:
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
    return orchestrator.run(
        project_id=project_id,
        mr_iid=mr_iid,
        extra_diff=extra_diff,
        force_full=force_full,
    )


@router.get("/health")
def health():
    return {"status": "ok"}


@router.get("/health/detail")
def health_detail():
    from app.config import GITLAB_URL, LLM_PROVIDER, LLM_MODEL, REVIEW_MAX_CONCURRENT
    return {
        "status": "ok",
        "gitlab_url": GITLAB_URL,
        "token_set": bool(AICR_BOT_TOKEN),
        "llm_provider": LLM_PROVIDER,
        "llm_model": LLM_MODEL,
        "llm_key_set": bool(LLM_API_KEY),
        "review_auth_required": bool(REVIEW_API_SECRET),
        "review_api_allow_insecure": REVIEW_API_ALLOW_INSECURE,
        "review_max_concurrent": REVIEW_MAX_CONCURRENT,
        "incremental_review": AICR_INCREMENTAL_REVIEW,
    }


@router.post("/review", response_model=ReviewResult)
def review(req: ReviewRequest, request: Request):
    _verify_review_auth(request)

    try:
        acquire_review_slot()
    except ReviewCapacityError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    try:
        try:
            result = _run_orchestrator(
                req.project_id, req.mr_iid, req.diff, force_full=req.force_full
            )
        except NoReviewableChangesError as e:
            logger.info(f"No reviewable changes: {e}")
            return ReviewResult(
                score=FAIL_OPEN_SCORE,
                issues=[],
                summary=str(e),
                review_completed=False,
            )
        except HTTPException as e:
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
            review_completed=result.get("review_completed", False),
        )
    finally:
        release_review_slot()


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
        if not token or not secrets.compare_digest(token, GITLAB_WEBHOOK_SECRET):
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
            acquire_review_slot()
        except ReviewCapacityError as e:
            logger.error(f"Webhook review skipped (capacity): {e}")
            return
        try:
            _run_orchestrator(project_id, mr_iid)
        except Exception as e:
            logger.error(f"Webhook review failed: {e}", exc_info=True)
        finally:
            release_review_slot()

    background_tasks.add_task(_run_review)
    return {"status": "accepted", "project_id": project_id, "mr_iid": mr_iid}

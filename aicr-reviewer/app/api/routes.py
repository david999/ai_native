import logging
from fastapi import APIRouter, BackgroundTasks, Request, HTTPException
from pydantic import BaseModel
from typing import List, Dict

from app.config import AICR_BOT_TOKEN, GITLAB_WEBHOOK_SECRET, LLM_API_KEY
from app.review.orchestrator import ReviewOrchestrator
from app.gitlab.context_builder import ContextBuilder
from app.llm.factory import create_llm_provider
from app.gitlab.publisher import GitLabPublisher

logger = logging.getLogger("aicr")
router = APIRouter()


class ReviewRequest(BaseModel):
    project_id: int
    mr_iid: int
    diff: str = ""


class ReviewResult(BaseModel):
    score: float
    issues: List[Dict]
    code_quality: List[Dict] = []
    summary: str = ""


@router.get("/health")
def health():
    from app.config import GITLAB_URL, LLM_PROVIDER, LLM_MODEL
    return {
        "status": "ok",
        "gitlab_url": GITLAB_URL,
        "token_set": bool(AICR_BOT_TOKEN),
        "llm_provider": LLM_PROVIDER,
        "llm_model": LLM_MODEL,
        "llm_key_set": bool(LLM_API_KEY) if LLM_PROVIDER else False,
    }


@router.post("/review", response_model=ReviewResult)
def review(req: ReviewRequest):
    if not AICR_BOT_TOKEN:
        raise HTTPException(status_code=500, detail="AICR_BOT_TOKEN is not set")

    try:
        llm = create_llm_provider()
    except ValueError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    try:
        orchestrator = ReviewOrchestrator(
            context_builder=ContextBuilder(),
            llm_provider=llm,
            publisher=GitLabPublisher(),
        )
        result = orchestrator.run(project_id=req.project_id, mr_iid=req.mr_iid, extra_diff=req.diff)
    except Exception as e:
        logger.error(f"Review failed: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Review failed: {e}") from e

    return ReviewResult(
        score=result["score"],
        issues=result["issues"],
        code_quality=result.get("code_quality", []),
        summary=result.get("summary", ""),
    )


@router.post("/webhook/gitlab")
async def gitlab_webhook(request: Request, background_tasks: BackgroundTasks):
    body = await request.json()
    token = request.headers.get("X-Gitlab-Token", "")

    if GITLAB_WEBHOOK_SECRET and token != GITLAB_WEBHOOK_SECRET:
        logger.warning("Webhook token mismatch, rejecting")
        return {"status": "rejected"}

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
            orchestrator = ReviewOrchestrator(
                context_builder=ContextBuilder(),
                llm_provider=create_llm_provider(),
                publisher=GitLabPublisher(),
            )
            orchestrator.run(project_id=project_id, mr_iid=mr_iid)
        except Exception as e:
            logger.error(f"Webhook review failed: {e}", exc_info=True)

    background_tasks.add_task(_run_review)
    return {"status": "accepted", "project_id": project_id, "mr_iid": mr_iid}

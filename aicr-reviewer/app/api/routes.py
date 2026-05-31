import logging
import secrets
from fastapi import APIRouter, BackgroundTasks, Request, HTTPException
from pydantic import BaseModel
from typing import List, Dict

from app.config import (
    AICR_ASK_ENABLED,
    AICR_BOT_TOKEN,
    AICR_CHANGELOG_ENABLED,
    AICR_DESCRIBE_ENABLED,
    AICR_INCREMENTAL_REVIEW,
    AICR_WEBHOOK_NOTE_ENABLED,
    GITLAB_WEBHOOK_SECRET,
    GITLAB_WEBHOOK_ALLOW_INSECURE,
    LLM_API_KEY,
    REVIEW_API_SECRET,
    REVIEW_API_ALLOW_INSECURE,
)
from app.api.concurrency import (
    acquire_mr_review,
    acquire_review_slot,
    release_mr_review,
    release_review_slot,
    MRReviewBusyError,
    ReviewCapacityError,
)
from app.review.review_state import ReviewStateStore
from app.exceptions import LLMReviewError, NoReviewableChangesError, ReviewError
from app.review.orchestrator import ReviewOrchestrator
from app.gitlab.context_builder import ContextBuilder
from app.llm.factory import create_llm_provider
from app.gitlab.publisher import GitLabPublisher
from app.tools.describe import DescribeTool
from app.tools.changelog import ChangelogTool
from app.config_resolver import ask_triggers_for_project, bot_username_for_project
from app.tools.ask import AskTool, should_respond_to_note, extract_user_question

logger = logging.getLogger("aicr")
router = APIRouter()

FAIL_OPEN_SCORE = 100.0


class ReviewRequest(BaseModel):
    project_id: int
    mr_iid: int
    diff: str = ""
    force_full: bool = False


class DescribeRequest(BaseModel):
    project_id: int
    mr_iid: int
    update_mr: bool | None = None


class DescribeResult(BaseModel):
    title: str = ""
    description: str = ""
    updated_mr: bool = False
    dry_run: bool = False
    webhook_review_suppressed: bool = False


class ChangelogRequest(BaseModel):
    project_id: int
    mr_iid: int


class ChangelogResult(BaseModel):
    summary: str = ""
    changelog: str = ""
    posted_note: bool = False
    updated_note: bool = False
    unchanged_note: bool = False
    note_action: str = "skipped"
    dry_run: bool = False


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

    state_store = ReviewStateStore()
    orchestrator = ReviewOrchestrator(
        context_builder=ContextBuilder(state_store=state_store),
        llm_provider=llm,
        publisher=GitLabPublisher(),
        state_store=state_store,
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
        "describe_enabled": AICR_DESCRIBE_ENABLED,
        "changelog_enabled": AICR_CHANGELOG_ENABLED,
        "ask_enabled": AICR_ASK_ENABLED,
        "webhook_note_enabled": AICR_WEBHOOK_NOTE_ENABLED,
    }


def _make_context_builder() -> ContextBuilder:
    return ContextBuilder(state_store=ReviewStateStore())


def _create_llm_or_raise() -> object:
    try:
        return create_llm_provider()
    except ValueError as e:
        raise HTTPException(status_code=503, detail="LLM provider not configured") from e


def _run_describe(project_id: int, mr_iid: int, update_mr: bool | None) -> dict:
    _create_llm_or_raise()
    tool = DescribeTool(_make_context_builder())
    return tool.run(project_id, mr_iid, update_mr=update_mr)


def _run_changelog(project_id: int, mr_iid: int) -> dict:
    _create_llm_or_raise()
    tool = ChangelogTool(_make_context_builder())
    return tool.run(project_id, mr_iid)


def _run_ask(
    project_id: int,
    mr_iid: int,
    question: str,
    *,
    thread_context: str = "",
    discussion_id: str | None = None,
) -> dict:
    _create_llm_or_raise()
    builder = _make_context_builder()
    if discussion_id and not thread_context:
        from app.gitlab.mr_actions import GitLabMRActions

        thread_context = GitLabMRActions().fetch_discussion_context(
            project_id, mr_iid, discussion_id
        )
    tool = AskTool(builder)
    return tool.run(
        project_id,
        mr_iid,
        question,
        thread_context=thread_context,
        discussion_id=discussion_id,
    )


@router.post("/review", response_model=ReviewResult)
def review(req: ReviewRequest, request: Request):
    _verify_review_auth(request)

    try:
        acquire_review_slot()
    except ReviewCapacityError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    try:
        acquire_mr_review(req.project_id, req.mr_iid)
    except MRReviewBusyError as e:
        release_review_slot()
        raise HTTPException(status_code=409, detail=str(e)) from e

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
        release_mr_review(req.project_id, req.mr_iid)
        release_review_slot()


@router.post("/describe", response_model=DescribeResult)
def describe(req: DescribeRequest, request: Request):
    _verify_review_auth(request)
    if not AICR_DESCRIBE_ENABLED:
        raise HTTPException(status_code=503, detail="AICR_DESCRIBE_ENABLED=0")

    if not AICR_BOT_TOKEN:
        raise HTTPException(status_code=500, detail="AICR_BOT_TOKEN is not configured")

    try:
        acquire_review_slot()
    except ReviewCapacityError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    try:
        acquire_mr_review(req.project_id, req.mr_iid)
    except MRReviewBusyError as e:
        release_review_slot()
        raise HTTPException(status_code=409, detail=str(e)) from e

    try:
        try:
            result = _run_describe(req.project_id, req.mr_iid, req.update_mr)
        except NoReviewableChangesError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except HTTPException:
            raise
        except (LLMReviewError, ReviewError) as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return DescribeResult(**result)
    finally:
        release_mr_review(req.project_id, req.mr_iid)
        release_review_slot()


@router.post("/changelog", response_model=ChangelogResult)
def changelog(req: ChangelogRequest, request: Request):
    _verify_review_auth(request)
    if not AICR_CHANGELOG_ENABLED:
        raise HTTPException(status_code=503, detail="AICR_CHANGELOG_ENABLED=0")

    if not AICR_BOT_TOKEN:
        raise HTTPException(status_code=500, detail="AICR_BOT_TOKEN is not configured")

    try:
        acquire_review_slot()
    except ReviewCapacityError as e:
        raise HTTPException(status_code=503, detail=str(e)) from e

    try:
        acquire_mr_review(req.project_id, req.mr_iid)
    except MRReviewBusyError as e:
        release_review_slot()
        raise HTTPException(status_code=409, detail=str(e)) from e

    try:
        try:
            result = _run_changelog(req.project_id, req.mr_iid)
        except NoReviewableChangesError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except (LLMReviewError, ReviewError) as e:
            raise HTTPException(status_code=502, detail=str(e)) from e
        return ChangelogResult(**result)
    finally:
        release_mr_review(req.project_id, req.mr_iid)
        release_review_slot()


def _verify_gitlab_webhook(request: Request) -> None:
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


def _schedule_mr_review(
    background_tasks: BackgroundTasks,
    project_id: int,
    mr_iid: int,
) -> None:
    def _run_review():
        state = ReviewStateStore()
        if state.is_webhook_review_suppressed(project_id, mr_iid):
            logger.info(
                f"Webhook review skipped: MR !{mr_iid} suppressed after describe"
            )
            return
        try:
            acquire_review_slot()
        except ReviewCapacityError as e:
            logger.error(f"Webhook review skipped (capacity): {e}")
            return
        try:
            acquire_mr_review(project_id, mr_iid)
        except MRReviewBusyError:
            logger.info(
                f"Webhook review skipped: MR !{mr_iid} already in progress"
            )
            return
        try:
            _run_orchestrator(project_id, mr_iid)
        except Exception as e:
            logger.error(f"Webhook review failed: {e}", exc_info=True)
        finally:
            release_mr_review(project_id, mr_iid)
            release_review_slot()

    background_tasks.add_task(_run_review)


def _schedule_note_ask(
    background_tasks: BackgroundTasks,
    project_id: int,
    mr_iid: int,
    note_body: str,
    *,
    author_username: str,
    discussion_id: str | None,
    project_config: dict | None = None,
) -> None:
    def _note_ask_task():
        if not AICR_ASK_ENABLED or not AICR_WEBHOOK_NOTE_ENABLED:
            return
        try:
            acquire_review_slot()
        except ReviewCapacityError as e:
            logger.error(f"Note ask skipped (capacity): {e}")
            return
        try:
            acquire_mr_review(project_id, mr_iid)
        except MRReviewBusyError:
            logger.info(f"Note ask skipped: MR !{mr_iid} busy")
            return
        try:
            triggers = ask_triggers_for_project(project_config)
            question = extract_user_question(note_body, triggers=triggers)
            logger.info(
                f"Note ask from @{author_username} on MR !{mr_iid}: "
                f"{question[:80]!r}..."
            )
            _run_ask(
                project_id,
                mr_iid,
                question,
                discussion_id=discussion_id,
            )
        except Exception as e:
            logger.error(f"Note ask failed: {e}", exc_info=True)
        finally:
            release_mr_review(project_id, mr_iid)
            release_review_slot()

    background_tasks.add_task(_note_ask_task)


@router.post("/webhook/gitlab")
async def gitlab_webhook(request: Request, background_tasks: BackgroundTasks):
    _verify_gitlab_webhook(request)
    body = await request.json()
    object_kind = body.get("object_kind", "")

    if object_kind == "note":
        if not AICR_WEBHOOK_NOTE_ENABLED or not AICR_ASK_ENABLED:
            return {"status": "ignored", "reason": "note webhook disabled"}

        attrs = body.get("object_attributes", {})
        note_action = attrs.get("action", "create")
        if note_action not in ("create",):
            return {"status": "ignored", "reason": f"note action: {note_action}"}

        if attrs.get("noteable_type") != "MergeRequest":
            return {
                "status": "ignored",
                "reason": f"noteable_type: {attrs.get('noteable_type')}",
            }

        note_body = attrs.get("note", "") or ""
        author_username = (body.get("user") or {}).get("username", "")
        is_system = bool(attrs.get("system"))

        project_id = body.get("project", {}).get("id")
        mr_iid = (body.get("merge_request") or {}).get("iid")
        if not project_id or not mr_iid:
            return {"status": "ignored", "reason": "missing project_id or mr_iid"}

        project_config: dict = {}
        try:
            from app.config_toml import load_project_config_from_repo
            from app.gitlab.session import GitLabMRSession

            gl_session = GitLabMRSession(project_id, mr_iid)
            project_config = load_project_config_from_repo(
                gl_session.project, gl_session.mr
            )
        except Exception as e:
            logger.debug(f"Project config not loaded for note webhook: {e}")

        bot_user = bot_username_for_project(project_config)
        triggers = ask_triggers_for_project(project_config)
        if not should_respond_to_note(
            note_body,
            author_username=author_username,
            is_system_note=is_system,
            triggers=triggers,
            bot_username=bot_user,
        ):
            return {"status": "ignored", "reason": "no trigger or bot note"}

        discussion_id = attrs.get("discussion_id") or attrs.get("discussion", {}).get("id")
        _schedule_note_ask(
            background_tasks,
            project_id,
            mr_iid,
            note_body,
            author_username=author_username,
            discussion_id=str(discussion_id) if discussion_id else None,
            project_config=project_config,
        )
        return {
            "status": "accepted",
            "kind": "note",
            "project_id": project_id,
            "mr_iid": mr_iid,
        }

    if object_kind != "merge_request":
        return {"status": "ignored", "reason": f"not merge_request: {object_kind}"}

    action = body.get("object_attributes", {}).get("action", "")
    if action not in ("open", "update", "reopen"):
        return {"status": "ignored", "reason": f"action: {action}"}

    project_id = body.get("project", {}).get("id")
    mr_iid = body.get("object_attributes", {}).get("iid")
    if not project_id or not mr_iid:
        return {"status": "ignored", "reason": "missing project_id or mr_iid"}

    _schedule_mr_review(background_tasks, project_id, mr_iid)
    return {"status": "accepted", "project_id": project_id, "mr_iid": mr_iid}

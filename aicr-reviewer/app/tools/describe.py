"""生成 MR 标题/描述（describe 工具）。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.config import AICR_DESCRIBE_UPDATE_MR, REVIEW_DRY_RUN
from app.exceptions import LLMReviewError, NoReviewableChangesError
from app.gitlab.context_builder import ContextBuilder
from app.gitlab.mr_actions import GitLabMRActions
from app.gitlab.session import GitLabMRSession
from app.llm.base import LLMProvider
from app.review.language_priority import infer_language_hint
from app.review.prompt_renderer import PromptRenderer
from app.tools.diff_text import build_diff_text_from_context, changed_files_summary
from app.tools.tool_parser import ToolResponseParser

logger = logging.getLogger("aicr")


class DescribeTool:
    def __init__(
        self,
        context_builder: ContextBuilder,
        llm: LLMProvider,
        actions: Optional[GitLabMRActions] = None,
    ):
        self.context_builder = context_builder
        self.llm = llm
        self.actions = actions or GitLabMRActions()
        self.renderer = PromptRenderer()
        self.parser = ToolResponseParser()

    def run(
        self,
        project_id: int,
        mr_iid: int,
        *,
        update_mr: Optional[bool] = None,
    ) -> Dict[str, Any]:
        gl_session = GitLabMRSession(project_id, mr_iid)
        ctx = self.context_builder.build(
            project_id, mr_iid, session=gl_session, force_full=True
        )
        supported = [f for f in ctx.changed_files if f.get("is_supported")]
        if not supported and not ctx.deleted_files:
            raise NoReviewableChangesError("No supported changes for describe")

        language_hint = infer_language_hint(
            ctx.changed_files or [{"new_path": p} for p in ctx.deleted_files]
        )
        diff_text = build_diff_text_from_context(ctx)
        system_prompt = self.renderer.render_describe_system(
            context_md=ctx.context_md, language_hint=language_hint
        )
        user_prompt = self.renderer.render_describe_user(
            mr_title=ctx.title,
            mr_description=ctx.description,
            changed_files_summary=changed_files_summary(ctx),
            diff_text=diff_text,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            raw = self.llm.chat(messages, json_mode=True)
            parsed = self.parser.parse_describe(raw)
        except Exception as e:
            raise LLMReviewError(f"Describe failed: {e}") from e

        should_update = (
            AICR_DESCRIBE_UPDATE_MR if update_mr is None else update_mr
        )
        updated = False
        if should_update and not REVIEW_DRY_RUN:
            title = parsed["title"] or None
            updated = self.actions.update_mr_description(
                project_id,
                mr_iid,
                description=parsed["description"],
                title=title,
                session=gl_session,
            )

        return {
            "title": parsed["title"],
            "description": parsed["description"],
            "updated_mr": updated,
            "dry_run": REVIEW_DRY_RUN,
        }

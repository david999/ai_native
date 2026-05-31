"""生成 CHANGELOG 条目并发布为 MR note。"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from app.config import REVIEW_DRY_RUN
from app.exceptions import LLMReviewError, NoReviewableChangesError
from app.gitlab.context_builder import ContextBuilder
from app.gitlab.mr_actions import GitLabMRActions
from app.gitlab.session import GitLabMRSession
from app.llm.base import LLMProvider
from app.review.prompt_renderer import PromptRenderer
from app.tools.diff_text import build_diff_text_from_context, changed_files_summary
from app.tools.tool_parser import ToolResponseParser

logger = logging.getLogger("aicr")


class ChangelogTool:
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
    ) -> Dict[str, Any]:
        gl_session = GitLabMRSession(project_id, mr_iid)
        ctx = self.context_builder.build(
            project_id, mr_iid, session=gl_session, force_full=True
        )
        supported = [f for f in ctx.changed_files if f.get("is_supported")]
        if not supported and not ctx.deleted_files:
            raise NoReviewableChangesError("No supported changes for changelog")

        diff_text = build_diff_text_from_context(ctx)
        system_prompt = self.renderer.render_changelog_system(context_md=ctx.context_md)
        user_prompt = self.renderer.render_changelog_user(
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
            parsed = self.parser.parse_changelog(raw)
        except Exception as e:
            raise LLMReviewError(f"Changelog failed: {e}") from e

        note_body = (
            "## AICR Changelog\n\n"
            f"**Summary:** {parsed['summary']}\n\n"
            f"{parsed['changelog']}\n"
        )
        posted = False
        if not REVIEW_DRY_RUN:
            posted = self.actions.post_note(
                project_id, mr_iid, note_body, session=gl_session
            )

        return {
            "summary": parsed["summary"],
            "changelog": parsed["changelog"],
            "posted_note": posted,
            "dry_run": REVIEW_DRY_RUN,
        }

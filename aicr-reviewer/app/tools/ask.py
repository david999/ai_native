"""MR 评论对话（@aicr / /ask）。"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from app.config import AICR_ASK_TRIGGERS, AICR_BOT_USERNAME
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

_AICR_REPLY_PREFIX = "**AICR**"


def should_respond_to_note(
    note_body: str,
    *,
    author_username: str = "",
    is_system_note: bool = False,
    triggers: Optional[List[str]] = None,
    bot_username: str = "",
) -> bool:
    if is_system_note:
        return False
    body = (note_body or "").strip()
    if not body:
        return False
    if body.startswith(_AICR_REPLY_PREFIX):
        return False

    bot = (bot_username or AICR_BOT_USERNAME).lower()
    author = (author_username or "").lower()
    if bot and author and author == bot:
        return False

    trigger_list = triggers or AICR_ASK_TRIGGERS
    lower = body.lower()
    for t in trigger_list:
        token = t.strip().lower()
        if not token:
            continue
        if token.startswith("/"):
            if re.search(rf"(?:^|\s){re.escape(token)}(?:\s|$)", lower):
                return True
        elif token in lower:
            return True
    return False


def extract_user_question(note_body: str, triggers: Optional[List[str]] = None) -> str:
    text = (note_body or "").strip()
    trigger_list = triggers or AICR_ASK_TRIGGERS
    for t in trigger_list:
        token = t.strip()
        if not token:
            continue
        if token.lower() in text.lower():
            idx = text.lower().find(token.lower())
            text = text[idx + len(token) :].strip()
            break
    return text or note_body.strip()


class AskTool:
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
        user_question: str,
        *,
        thread_context: str = "",
        discussion_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        gl_session = GitLabMRSession(project_id, mr_iid)
        ctx = self.context_builder.build(
            project_id, mr_iid, session=gl_session, force_full=True
        )
        supported = [f for f in ctx.changed_files if f.get("is_supported")]
        if not supported and not ctx.deleted_files:
            raise NoReviewableChangesError("No supported changes for ask")

        language_hint = infer_language_hint(
            ctx.changed_files or [{"new_path": p} for p in ctx.deleted_files]
        )
        diff_text = build_diff_text_from_context(ctx)
        system_prompt = self.renderer.render_ask_system(
            context_md=ctx.context_md, language_hint=language_hint
        )
        user_prompt = self.renderer.render_ask_user(
            mr_title=ctx.title,
            mr_description=ctx.description,
            changed_files_summary=changed_files_summary(ctx),
            diff_text=diff_text,
            user_question=user_question,
            thread_context=thread_context,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            raw = self.llm.chat(messages, json_mode=True)
            parsed = self.parser.parse_ask(raw)
        except Exception as e:
            raise LLMReviewError(f"Ask failed: {e}") from e

        reply_body = f"{_AICR_REPLY_PREFIX}\n\n{parsed['answer']}"
        from app.config import REVIEW_DRY_RUN

        replied = False
        if not REVIEW_DRY_RUN:
            if discussion_id:
                replied = self.actions.reply_to_note(
                    project_id,
                    mr_iid,
                    discussion_id,
                    reply_body,
                    session=gl_session,
                )
            else:
                replied = self.actions.post_note(
                    project_id, mr_iid, reply_body, session=gl_session
                )

        return {
            "answer": parsed["answer"],
            "replied": replied,
            "dry_run": REVIEW_DRY_RUN,
        }

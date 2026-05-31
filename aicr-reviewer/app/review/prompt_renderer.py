"""使用 Jinja2 渲染 system/user 评审提示词（模板位于 prompts/）。"""

import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.review.language_priority import resolve_system_template

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")
_env = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    autoescape=select_autoescape(default_for_string=False, default=False),
)


class PromptRenderer:
    def render_system(self, context_md: str = "", language_hint: str = "General") -> str:
        template_name = resolve_system_template(language_hint)
        template = _env.get_template(template_name)
        return template.render(context_md=context_md, language_hint=language_hint)

    def render_user(
        self,
        mr_title: str = "",
        mr_description: str = "",
        changed_files_summary: str = "",
        diff_text: str = "",
    ) -> str:
        template = _env.get_template("user_review.j2")
        return template.render(
            mr_title=mr_title,
            mr_description=mr_description,
            changed_files_summary=changed_files_summary,
            diff_text=diff_text,
        )

    def render_reflection_system(
        self, context_md: str = "", language_hint: str = "General"
    ) -> str:
        template = _env.get_template("reflection_system.j2")
        return template.render(context_md=context_md, language_hint=language_hint)

    def render_reflection_user(
        self,
        *,
        mr_title: str = "",
        mr_description: str = "",
        diff_text: str = "",
        initial_review_json: str = "",
    ) -> str:
        template = _env.get_template("reflection_user.j2")
        return template.render(
            mr_title=mr_title,
            mr_description=mr_description,
            diff_text=diff_text,
            initial_review_json=initial_review_json,
        )

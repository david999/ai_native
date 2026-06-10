"""使用 Jinja2 渲染 system/user 评审提示词（模板位于 prompts/）。"""

import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.review.prompt_variants import resolve_effective_system_template

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")
_env = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    autoescape=select_autoescape(default_for_string=False, default=False),
)


class PromptRenderer:
    def render_system(
        self,
        context_md: str = "",
        language_hint: str = "General",
        *,
        template_override: str | None = None,
        strict_override: bool = False,
    ) -> tuple[str, str]:
        """返回 (template_name, rendered_text)。需要仅文本时请用 render_system_text()。"""
        template_name = resolve_effective_system_template(
            language_hint,
            override=template_override,
            strict_override=strict_override,
        )
        template = _env.get_template(template_name)
        text = template.render(context_md=context_md, language_hint=language_hint)
        return template_name, text

    def render_system_text(
        self,
        context_md: str = "",
        language_hint: str = "General",
        *,
        template_override: str | None = None,
        strict_override: bool = False,
    ) -> str:
        """兼容包装：仅返回渲染后的 system 文本。"""
        _name, text = self.render_system(
            context_md=context_md,
            language_hint=language_hint,
            template_override=template_override,
            strict_override=strict_override,
        )
        return text

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

    def render_describe_system(self, context_md: str = "", language_hint: str = "General") -> str:
        template = _env.get_template("describe_system.j2")
        return template.render(context_md=context_md, language_hint=language_hint)

    def render_describe_user(
        self,
        *,
        mr_title: str = "",
        mr_description: str = "",
        changed_files_summary: str = "",
        diff_text: str = "",
    ) -> str:
        template = _env.get_template("describe_user.j2")
        return template.render(
            mr_title=mr_title,
            mr_description=mr_description,
            changed_files_summary=changed_files_summary,
            diff_text=diff_text,
        )

    def render_changelog_system(self, context_md: str = "") -> str:
        template = _env.get_template("changelog_system.j2")
        return template.render(context_md=context_md)

    def render_changelog_user(
        self,
        *,
        mr_title: str = "",
        mr_description: str = "",
        changed_files_summary: str = "",
        diff_text: str = "",
    ) -> str:
        template = _env.get_template("changelog_user.j2")
        return template.render(
            mr_title=mr_title,
            mr_description=mr_description,
            changed_files_summary=changed_files_summary,
            diff_text=diff_text,
        )

    def render_ask_system(self, context_md: str = "", language_hint: str = "General") -> str:
        template = _env.get_template("ask_system.j2")
        return template.render(context_md=context_md, language_hint=language_hint)

    def render_ask_user(
        self,
        *,
        mr_title: str = "",
        mr_description: str = "",
        changed_files_summary: str = "",
        diff_text: str = "",
        user_question: str = "",
        thread_context: str = "",
    ) -> str:
        template = _env.get_template("ask_user.j2")
        return template.render(
            mr_title=mr_title,
            mr_description=mr_description,
            changed_files_summary=changed_files_summary,
            diff_text=diff_text,
            user_question=user_question,
            thread_context=thread_context,
        )

import os
from jinja2 import Environment, FileSystemLoader, select_autoescape

_PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")
_env = Environment(
    loader=FileSystemLoader(_PROMPTS_DIR),
    autoescape=select_autoescape(default_for_string=False, default=False),
)


class PromptRenderer:
    def render_system(self, context_md: str = "", language_hint: str = "Java/Spring") -> str:
        template = _env.get_template("system_spring.j2")
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

import logging
from typing import Optional

from app.gitlab.client import get_gitlab_client
from app.config import CONTEXT_MAX_CHARS, SCORE_THRESHOLD
from app.utils.redact import redact_secrets

logger = logging.getLogger("aicr")

SUPPORTED_EXTENSIONS = (
    ".java", ".kt", ".xml", ".yml", ".yaml", ".properties",
    ".py", ".js", ".ts", ".go", ".rs", ".sql",
    ".dockerfile", ".gradle", ".toml",
)


class MRContext:
    __slots__ = (
        "project_id", "mr_iid", "title", "description",
        "source_branch", "target_branch", "diff_refs",
        "changes", "context_md", "changed_files",
    )

    def __init__(self):
        self.project_id: int = 0
        self.mr_iid: int = 0
        self.title: str = ""
        self.description: str = ""
        self.source_branch: str = ""
        self.target_branch: str = ""
        self.diff_refs: Optional[dict] = None
        self.changes: list = []
        self.context_md: str = ""
        self.changed_files: list = []


class ContextBuilder:
    """拉取 MR 变更列表，过滤 SUPPORTED_EXTENSIONS，并加载项目 LLM 上下文文档。"""

    def build(self, project_id: int, mr_iid: int, extra_diff: str = "") -> MRContext:
        gl = get_gitlab_client()
        project = gl.projects.get(project_id)
        mr = project.mergerequests.get(mr_iid)

        ctx = MRContext()
        ctx.project_id = project_id
        ctx.mr_iid = mr_iid
        ctx.title = mr.title or ""
        ctx.description = mr.description or ""
        ctx.source_branch = mr.source_branch
        ctx.target_branch = mr.target_branch
        ctx.diff_refs = mr.diff_refs

        changes_data = mr.changes()
        ctx.changes = changes_data.get("changes", [])

        ctx.changed_files = []
        for change in ctx.changes:
            new_path = change.get("new_path") or ""
            old_path = change.get("old_path") or ""
            diff_text = change.get("diff", "")
            is_supported = new_path.endswith(SUPPORTED_EXTENSIONS) or old_path.endswith(SUPPORTED_EXTENSIONS)

            file_content = ""
            if is_supported and new_path:
                try:
                    raw = project.files.raw(file_path=new_path, ref=mr.source_branch)
                    file_content = raw.decode("utf-8", errors="ignore")
                except Exception as ex:
                    logger.debug(f"Skip full file {new_path}: {ex}")

            ctx.changed_files.append({
                "old_path": old_path,
                "new_path": new_path,
                "diff": diff_text,
                "content": file_content,
                "is_supported": is_supported,
            })

        if extra_diff:
            ctx.changed_files.insert(0, {
                "old_path": "",
                "new_path": "_ci_extra_diff.patch",
                "diff": extra_diff,
                "content": "",
                "is_supported": True,
            })

        ctx.context_md = redact_secrets(self._load_context_md(project, mr))

        logger.info(
            f"MR !{mr_iid} context: {len(ctx.changed_files)} files, "
            f"context_md={len(ctx.context_md)} chars"
        )
        return ctx

    def _load_context_md(self, project, mr) -> str:
        for ref in (mr.source_branch, mr.target_branch):
            try:
                raw = project.files.raw(file_path=".llm/CONTEXT.md", ref=ref)
                content = raw.decode("utf-8", errors="ignore")
                if len(content) > CONTEXT_MAX_CHARS:
                    logger.warning(
                        f".llm/CONTEXT.md ({len(content)} chars) exceeds "
                        f"CONTEXT_MAX_CHARS={CONTEXT_MAX_CHARS}, truncating"
                    )
                    content = content[:CONTEXT_MAX_CHARS]
                logger.info(f"Loaded .llm/CONTEXT.md from ref={ref}")
                return content
            except Exception:
                continue

        logger.info("Using built-in default context (no .llm/CONTEXT.md found)")
        return self._default_context()

    @staticmethod
    def _default_context() -> str:
        return (
            "## Project Context (default)\n\n"
            "This is a Spring Boot / Spring Cloud Java project.\n\n"
            "### Key Conventions\n"
            "- Use constructor injection over @Autowired field injection\n"
            "- @Transactional must not be called via self-invocation (proxy bypass)\n"
            "- Feign clients must not be called inside loops (N+1 risk)\n"
            "- Never hardcode secrets; use Spring config or vault\n"
            "- RestTemplate / WebClient must configure connect and read timeouts\n"
            "- Use Optional or null-checks for values that may be absent\n"
            "- Prefer orElseThrow() over orElse(null) for Optional\n"
        )

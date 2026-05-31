import logging
from typing import Optional

from app.config import CONTEXT_MAX_CHARS
from app.gitlab.session import GitLabMRSession, gitlab_call
from app.utils.redact import redact_secrets

logger = logging.getLogger("aicr")

SUPPORTED_EXTENSIONS = (
    ".java", ".kt", ".xml", ".yml", ".yaml", ".properties",
    ".py", ".js", ".ts", ".go", ".rs", ".sql",
    ".dockerfile", ".gradle", ".toml",
)

# 无扩展名但常见的容器/构建文件
SPECIAL_FILENAMES = frozenset({"dockerfile", "makefile", "gemfile"})


def _is_supported_path(new_path: str, old_path: str) -> bool:
    for path in (new_path, old_path):
        if not path:
            continue
        lower = path.lower()
        if lower.endswith(SUPPORTED_EXTENSIONS):
            return True
        base = lower.rsplit("/", 1)[-1]
        if base in SPECIAL_FILENAMES:
            return True
    return False


class MRContext:
    __slots__ = (
        "project_id", "mr_iid", "title", "description",
        "source_branch", "target_branch", "diff_refs",
        "changes", "context_md", "changed_files", "gitlab_session",
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
        self.gitlab_session: Optional[GitLabMRSession] = None


class ContextBuilder:
    """拉取 MR 变更列表，过滤 SUPPORTED_EXTENSIONS，并加载项目 LLM 上下文文档。"""

    def build(
        self,
        project_id: int,
        mr_iid: int,
        extra_diff: str = "",
        session: Optional[GitLabMRSession] = None,
    ) -> MRContext:
        gl_session = session or GitLabMRSession(project_id, mr_iid)
        project = gl_session.project
        mr = gl_session.mr

        ctx = MRContext()
        ctx.project_id = project_id
        ctx.mr_iid = mr_iid
        ctx.gitlab_session = gl_session
        ctx.title = redact_secrets(mr.title or "")
        ctx.description = redact_secrets(mr.description or "")
        ctx.source_branch = mr.source_branch
        ctx.target_branch = mr.target_branch
        ctx.diff_refs = mr.diff_refs

        changes_data = gitlab_call(lambda: mr.changes())
        ctx.changes = changes_data.get("changes", [])

        ctx.changed_files = []
        for change in ctx.changes:
            new_path = change.get("new_path") or ""
            old_path = change.get("old_path") or ""
            diff_text = redact_secrets(change.get("diff", ""))
            is_supported = _is_supported_path(new_path, old_path)

            file_content = ""
            if is_supported and new_path:
                try:
                    raw = gitlab_call(
                        lambda np=new_path: project.files.raw(
                            file_path=np, ref=mr.source_branch
                        )
                    )
                    file_content = redact_secrets(
                        raw.decode("utf-8", errors="ignore")
                    )
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
                "diff": redact_secrets(extra_diff),
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
                raw = gitlab_call(
                    lambda r=ref: project.files.raw(
                        file_path=".llm/CONTEXT.md", ref=r
                    )
                )
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

import logging
from typing import Optional, Tuple

from app.config import (
    AICR_FETCH_FULL_FILE,
    AICR_FETCH_FULL_FILE_ON_INCREMENTAL,
    AICR_FORCE_FULL_REVIEW,
    AICR_INCREMENTAL_REVIEW,
    CONTEXT_MAX_CHARS,
)
from app.gitlab.session import GitLabMRSession, gitlab_call
from app.config_toml import load_project_config_from_repo
from app.review.diff_compress import compress_changes
from app.utils.redact import redact_secrets

logger = logging.getLogger("aicr")

SUPPORTED_EXTENSIONS = (
    ".java", ".kt", ".xml", ".yml", ".yaml", ".properties",
    ".py", ".js", ".ts", ".go", ".rs", ".sql",
    ".dockerfile", ".gradle", ".toml",
)

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
        "source_branch", "target_branch", "diff_refs", "head_sha",
        "changes", "context_md", "changed_files", "deleted_files",
        "incremental_from_sha", "skip_review", "skip_reason", "gitlab_session",
        "project_config",
    )

    def __init__(self):
        self.project_id: int = 0
        self.mr_iid: int = 0
        self.title: str = ""
        self.description: str = ""
        self.source_branch: str = ""
        self.target_branch: str = ""
        self.diff_refs: Optional[dict] = None
        self.head_sha: str = ""
        self.changes: list = []
        self.context_md: str = ""
        self.changed_files: list = []
        self.deleted_files: list = []
        self.incremental_from_sha: Optional[str] = None
        self.skip_review: bool = False
        self.skip_reason: str = ""
        self.gitlab_session: Optional[GitLabMRSession] = None
        self.project_config: dict = {}


class ContextBuilder:
    """拉取 MR 变更列表，过滤 SUPPORTED_EXTENSIONS，并加载项目 LLM 上下文文档。"""

    def __init__(self, state_store=None):
        from app.review.review_state import ReviewStateStore

        self._state_store = state_store or ReviewStateStore()

    def build(
        self,
        project_id: int,
        mr_iid: int,
        extra_diff: str = "",
        session: Optional[GitLabMRSession] = None,
        *,
        force_full: bool = False,
    ) -> MRContext:
        gl_session = session or GitLabMRSession(project_id, mr_iid)
        project = gl_session.project
        mr = gl_session.mr

        ctx = MRContext()
        ctx.project_id = project_id
        ctx.mr_iid = mr_iid
        ctx.gitlab_session = gl_session
        ctx.project_config = load_project_config_from_repo(project, mr)
        ctx.title = redact_secrets(mr.title or "")
        ctx.description = redact_secrets(mr.description or "")
        ctx.source_branch = mr.source_branch
        ctx.target_branch = mr.target_branch
        ctx.diff_refs = mr.diff_refs
        ctx.head_sha = self._resolve_head_sha(mr)

        raw_changes, incremental_from, unchanged = self._fetch_changes(
            project, mr, gl_session, force_full=force_full
        )
        ctx.incremental_from_sha = incremental_from
        if unchanged:
            ctx.skip_review = True
            ctx.skip_reason = (
                "No new commits since last successful review (head SHA unchanged)"
            )
            logger.info(f"MR !{mr_iid}: {ctx.skip_reason}")
            return ctx

        ctx.changes = raw_changes
        fetch_full_content = self._should_fetch_full_file(incremental_from is not None)

        compressed, deleted_paths = compress_changes(raw_changes)
        ctx.deleted_files = [
            p for p in deleted_paths
            if _is_supported_path(p, p) or _is_supported_path("", p)
        ]

        ctx.changed_files = []
        for change in compressed:
            new_path = change.get("new_path") or ""
            old_path = change.get("old_path") or ""
            diff_text = redact_secrets(change.get("diff", ""))
            is_supported = _is_supported_path(new_path, old_path)

            file_content = ""
            if fetch_full_content and is_supported and new_path:
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

        mode = "incremental" if incremental_from else "full"
        logger.info(
            f"MR !{mr_iid} context ({mode}): {len(ctx.changed_files)} files, "
            f"deleted={len(ctx.deleted_files)}, context_md={len(ctx.context_md)} chars"
        )
        return ctx

    @staticmethod
    def _resolve_head_sha(mr) -> str:
        refs = mr.diff_refs or {}
        head = refs.get("head_sha") or getattr(mr, "sha", None) or ""
        return str(head)

    @staticmethod
    def _should_fetch_full_file(is_incremental: bool) -> bool:
        if not AICR_FETCH_FULL_FILE:
            return False
        if is_incremental and not AICR_FETCH_FULL_FILE_ON_INCREMENTAL:
            return False
        return True

    def _fetch_changes(
        self,
        project,
        mr,
        gl_session: GitLabMRSession,
        *,
        force_full: bool,
    ) -> Tuple[list, Optional[str], bool]:
        """返回 (changes, incremental_from_sha, unchanged_since_last_review)。"""
        head_sha = self._resolve_head_sha(mr)
        use_incremental = (
            AICR_INCREMENTAL_REVIEW
            and not force_full
            and not AICR_FORCE_FULL_REVIEW
            and bool(head_sha)
        )

        if use_incremental:
            last_sha = self._state_store.get_last_reviewed_sha(
                gl_session.project_id, gl_session.mr_iid
            )
            if last_sha == head_sha:
                logger.info(
                    f"MR !{gl_session.mr_iid} head {head_sha[:8]} already reviewed"
                )
                return [], last_sha, True
            if last_sha and last_sha != head_sha:
                try:
                    compare = gitlab_call(
                        lambda: project.repository_compare(last_sha, head_sha)
                    )
                    diffs = compare.get("diffs") or []
                    if diffs:
                        logger.info(
                            f"Incremental compare {last_sha[:8]}..{head_sha[:8]}: "
                            f"{len(diffs)} file(s)"
                        )
                        return self._compare_diffs_to_changes(diffs), last_sha, False
                    logger.info("Incremental compare returned no diffs; using full MR")
                except Exception as e:
                    logger.warning(f"Incremental compare failed, full MR review: {e}")

        changes_data = gitlab_call(lambda: mr.changes())
        return changes_data.get("changes", []), None, False

    @staticmethod
    def _compare_diffs_to_changes(diffs: list) -> list:
        changes = []
        for d in diffs:
            changes.append({
                "old_path": d.get("old_path") or "",
                "new_path": d.get("new_path") or "",
                "diff": d.get("diff") or "",
                "new_file": d.get("new_file", False),
                "renamed_file": d.get("renamed_file", False),
                "deleted_file": d.get("deleted_file", False),
            })
        return changes

    def _load_context_md(self, project, mr) -> str:
        repo_text = self._fetch_repo_context_md(project, mr)
        if repo_text:
            return self._truncate_context(repo_text)
        
        logger.info("Using built-in default context (no .llm/CONTEXT.md found)")
        return self._default_context()


    def _fetch_repo_context_md(
        self, project, mr
    ) -> Optional[str]:
        for ref in (mr.source_branch, mr.target_branch):
            try:
                raw = gitlab_call(
                    lambda r=ref: project.files.raw(
                        file_path=".llm/CONTEXT.md", ref=r
                    )
                )
                content = raw.decode("utf-8", errors="ignore")
                logger.info(f"Loaded .llm/CONTEXT.md from ref={ref}")
                return content
            except Exception:
                continue
        return None

    @staticmethod
    def _truncate_context(content: str) -> str:
        if len(content) > CONTEXT_MAX_CHARS:
            logger.warning(
                f"Combined context ({len(content)} chars) exceeds "
                f"CONTEXT_MAX_CHARS={CONTEXT_MAX_CHARS}, truncating"
            )
            content = content[:CONTEXT_MAX_CHARS]
        return content

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

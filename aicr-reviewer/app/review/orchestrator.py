import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Any, List, Union

from app.config import (
    AICR_FILTER_ISSUES_TO_DIFF,
    REVIEW_CHUNK_MAX_WORKERS,
    REVIEW_DRY_RUN,
    SCORE_THRESHOLD,
)
from app.review.diff_line_index import filter_issues_to_diff
from app.review.reflection import run_reflection, should_reflect
from app.exceptions import LLMReviewError, NoReviewableChangesError
from app.gitlab.context_builder import ContextBuilder, MRContext, _is_supported_path
from app.gitlab.publisher import GitLabPublisher
from app.gitlab.session import GitLabMRSession
from app.llm.base import LLMProvider
from app.review.chunker import DiffChunker
from app.review.language_priority import infer_language_hint
from app.review.prompt_renderer import PromptRenderer
from app.review.parser import StructuredResponseParser, ParseError
from app.review.review_state import ReviewStateStore
from app.utils.redact import redact_secrets

logger = logging.getLogger("aicr")

_DELETIONS_PLACEHOLDER = "_aicr_deletions_review.md"


class ReviewOrchestrator:
    def __init__(
        self,
        context_builder: ContextBuilder,
        llm_provider: LLMProvider,
        publisher: GitLabPublisher,
        state_store: ReviewStateStore | None = None,
    ):
        self.context_builder = context_builder
        self.llm = llm_provider
        self.publisher = publisher
        self.state_store = state_store or ReviewStateStore()
        self.chunker = DiffChunker()
        self.renderer = PromptRenderer()
        self.parser = StructuredResponseParser()

    def run(
        self,
        project_id: int,
        mr_iid: int,
        extra_diff: str = "",
        *,
        force_full: bool = False,
    ) -> Dict[str, Any]:
        logger.info(f"Starting review for project={project_id} MR !{mr_iid}")

        gl_session = GitLabMRSession(project_id, mr_iid)
        ctx: MRContext = self.context_builder.build(
            project_id, mr_iid, extra_diff, session=gl_session, force_full=force_full
        )
        if getattr(ctx, "skip_review", False) is True:
            return self._skipped_result(ctx, gl_session)

        chunks = self._build_chunks(ctx)

        all_issues: list = []
        min_score = 100.0
        all_summaries: list = []
        llm_failures: list = []

        chunk_outcomes = self._review_all_chunks(ctx, chunks)
        for i, outcome in enumerate(chunk_outcomes):
            if isinstance(outcome, LLMReviewError):
                llm_failures.append(str(outcome))
                continue
            all_issues.extend(outcome.get("issues", []))
            chunk_score = outcome.get("score", 100.0)
            min_score = min(min_score, chunk_score)
            if outcome.get("summary"):
                all_summaries.append(outcome["summary"])

        if llm_failures and len(llm_failures) == len(chunks):
            raise LLMReviewError("; ".join(llm_failures))

        review_completed = len(llm_failures) == 0
        if llm_failures:
            all_summaries.append(
                f"Partial LLM failures ({len(llm_failures)}/{len(chunks)} chunks): "
                f"{'; '.join(llm_failures)}"
            )

        final_score, all_issues, all_summaries = self._finalize_findings(
            ctx, min_score, all_issues, all_summaries
        )
        summary = " | ".join(all_summaries) if all_summaries else "Review completed."

        publish_ok = True
        if not REVIEW_DRY_RUN:
            publish_ok = self._publish_results(ctx, gl_session, final_score, summary, all_issues)

        review_completed = review_completed and publish_ok

        if review_completed and ctx.head_sha and not REVIEW_DRY_RUN:
            self.state_store.set_last_reviewed_sha(project_id, mr_iid, ctx.head_sha)

        logger.info(
            f"Review complete: score={final_score}, issues={len(all_issues)}, "
            f"review_completed={review_completed}"
        )
        return {
            "score": final_score,
            "summary": summary,
            "issues": all_issues,
            "code_quality": self._build_code_quality(all_issues),
            "review_completed": review_completed,
        }

    def _skipped_result(
        self, ctx: MRContext, gl_session: GitLabMRSession
    ) -> Dict[str, Any]:
        summary = ctx.skip_reason or "Review skipped: no new changes"
        publish_ok = True
        if not REVIEW_DRY_RUN:
            publish_ok = self.publisher.publish_summary(
                project_id=ctx.project_id,
                mr_iid=ctx.mr_iid,
                score=100.0,
                summary=summary,
                issue_count=0,
                threshold=SCORE_THRESHOLD,
                session=gl_session,
            )
        return {
            "score": 100.0,
            "summary": summary,
            "issues": [],
            "code_quality": [],
            "review_completed": publish_ok,
        }

    def _review_all_chunks(
        self, ctx: MRContext, chunks: List[Dict]
    ) -> List[Union[Dict[str, Any], LLMReviewError]]:
        workers = min(REVIEW_CHUNK_MAX_WORKERS, len(chunks))
        if workers <= 1:
            return self._review_chunks_sequential(ctx, chunks)

        logger.info(f"Reviewing {len(chunks)} chunk(s) with {workers} worker(s)")
        outcomes: List[Union[Dict[str, Any], LLMReviewError]] = [
            LLMReviewError("not started")
        ] * len(chunks)

        def _run(i: int, chunk: Dict):
            logger.info(
                f"Reviewing chunk {i + 1}/{len(chunks)} "
                f"({chunk.get('total_tokens', chunk.get('total_chars', 0))} tokens est.)"
            )
            return self._review_chunk(ctx, chunk, chunk_index=i, total_chunks=len(chunks))

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(_run, i, chunk): i for i, chunk in enumerate(chunks)
            }
            for fut in as_completed(futures):
                i = futures[fut]
                try:
                    outcomes[i] = fut.result()
                except LLMReviewError as e:
                    outcomes[i] = e
                except Exception as e:
                    outcomes[i] = LLMReviewError(f"LLM call failed: {e}")
        return outcomes

    def _review_chunks_sequential(
        self, ctx: MRContext, chunks: List[Dict]
    ) -> List[Union[Dict[str, Any], LLMReviewError]]:
        outcomes: List[Union[Dict[str, Any], LLMReviewError]] = []
        for i, chunk in enumerate(chunks):
            logger.info(
                f"Reviewing chunk {i + 1}/{len(chunks)} "
                f"({chunk.get('total_tokens', chunk.get('total_chars', 0))} tokens est.)"
            )
            try:
                outcomes.append(
                    self._review_chunk(ctx, chunk, chunk_index=i, total_chunks=len(chunks))
                )
            except LLMReviewError as e:
                outcomes.append(e)
        return outcomes

    def _finalize_findings(
        self,
        ctx: MRContext,
        min_score: float,
        all_issues: list,
        all_summaries: list,
    ) -> tuple[float, list, list]:
        summaries = list(all_summaries)
        filter_opts = self._diff_filter_options(ctx)

        if AICR_FILTER_ISSUES_TO_DIFF and all_issues:
            all_issues, summaries = self._apply_diff_filter(
                all_issues, ctx.changed_files, summaries, filter_opts
            )

        language_hint = infer_language_hint(
            ctx.changed_files or [{"new_path": p} for p in ctx.deleted_files]
        )
        if should_reflect(min_score, all_issues):
            diff_text = redact_secrets(self._diff_text_for_reflection(ctx))
            initial = {
                "score": min_score,
                "summary": " | ".join(summaries) if summaries else "",
                "issues": all_issues,
            }
            reflected = run_reflection(
                self.llm,
                self.renderer,
                self.parser,
                language_hint=language_hint,
                context_md=ctx.context_md,
                mr_title=ctx.title,
                mr_description=ctx.description,
                diff_text=diff_text,
                initial=initial,
            )
            min_score = float(reflected.get("score", min_score))
            all_issues = reflected.get("issues", all_issues)
            if reflected.get("summary"):
                summaries.append(f"{reflected['summary']} (reflection)")

            if AICR_FILTER_ISSUES_TO_DIFF and all_issues:
                all_issues, summaries = self._apply_diff_filter(
                    all_issues, ctx.changed_files, summaries, filter_opts,
                    log_prefix="After reflection: ",
                )

        return min_score, all_issues, summaries

    @staticmethod
    def _diff_filter_options(ctx: MRContext) -> dict:
        """deletions-only 场景允许引用已删除路径的 issue。"""
        return {"additional_allowed_paths": list(ctx.deleted_files or [])}

    def _apply_diff_filter(
        self,
        issues: list,
        changed_files: list,
        summaries: list,
        filter_opts: dict,
        *,
        log_prefix: str = "",
    ) -> tuple[list, list]:
        kept, dropped = filter_issues_to_diff(
            issues,
            changed_files,
            additional_allowed_paths=filter_opts.get("additional_allowed_paths"),
        )
        if dropped:
            logger.info(
                f"{log_prefix}Filtered {len(dropped)} issue(s) outside MR diff hunks"
            )
            summaries = list(summaries)
            summaries.append(
                f"{log_prefix}Dropped {len(dropped)} issue(s) not in diff hunks"
            )
        return kept, summaries

    def _diff_text_for_reflection(self, ctx: MRContext) -> str:
        return self._build_diff_text(
            ctx.changed_files,
            deleted_files=ctx.deleted_files if ctx.deleted_files else None,
        )

    def _build_chunks(self, ctx: MRContext) -> List[Dict]:
        chunks = self.chunker.chunk_files(ctx.changed_files)
        if chunks:
            return chunks

        reviewable_deleted = [
            p for p in ctx.deleted_files
            if _is_supported_path(p, p) or _is_supported_path("", p)
        ]
        if reviewable_deleted:
            logger.info(
                f"MR !{ctx.mr_iid}: no diff chunks; reviewing {len(reviewable_deleted)} "
                "deleted/deletion-only path(s)"
            )
            return [self._deletions_only_chunk(reviewable_deleted)]

        raise NoReviewableChangesError(
            "No reviewable file changes in MR (supported extensions only)"
        )

    @staticmethod
    def _deletions_only_chunk(deleted_paths: List[str]) -> Dict:
        lines = "\n".join(f"- `{p}`" for p in deleted_paths)
        body = (
            "## Files removed or deletion-only changes\n\n"
            "The MR contains no added/modified hunks for supported file types, only "
            "deletions or deletion-only patches. Review whether removing this code "
            "introduces risk (e.g. lost auth checks, resource leaks).\n\n"
            f"{lines}\n"
        )
        return {
            "files": [{
                "old_path": "",
                "new_path": _DELETIONS_PLACEHOLDER,
                "diff": body,
                "content": "",
                "is_supported": True,
            }],
            "total_chars": len(body),
            "deletions_only": True,
        }

    def _review_chunk(
        self, ctx: MRContext, chunk: Dict, chunk_index: int = 0, total_chunks: int = 1
    ) -> Dict[str, Any]:
        language_hint = infer_language_hint(chunk["files"])
        system_prompt = self.renderer.render_system(
            context_md=ctx.context_md,
            language_hint=language_hint,
        )

        changed_files_summary = self._files_summary(chunk["files"])
        include_deleted = (
            chunk_index == 0
            and ctx.deleted_files
            and not chunk.get("deletions_only")
        )
        diff_text = redact_secrets(
            self._build_diff_text(
                chunk["files"],
                deleted_files=ctx.deleted_files if include_deleted else None,
            )
        )
        if ctx.incremental_from_sha:
            diff_text = (
                f"(Incremental review since `{ctx.incremental_from_sha[:8]}`)\n\n"
                + diff_text
            )

        chunk_note = ""
        if total_chunks > 1:
            chunk_note = (
                f"\n\nNote: chunk {chunk_index + 1}/{total_chunks}. "
                "Review only the files shown."
            )

        user_prompt = self.renderer.render_user(
            mr_title=ctx.title,
            mr_description=ctx.description,
            changed_files_summary=changed_files_summary,
            diff_text=diff_text,
        ) + chunk_note

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            raw = self.llm.chat(messages, json_mode=True)
        except Exception as e:
            raise LLMReviewError(f"LLM call failed: {e}") from e

        try:
            return self.parser.parse(raw)
        except ParseError as e:
            raise LLMReviewError(f"LLM response parse failed: {e}") from e

    def _publish_results(
        self,
        ctx: MRContext,
        gl_session: GitLabMRSession,
        score: float,
        summary: str,
        issues: list,
    ) -> bool:
        all_ok = True
        for issue in issues:
            file_path = issue.get("file", "")
            line = issue.get("line", 0)
            severity = issue.get("severity", "info")
            category = issue.get("category", "other")
            message = issue.get("message", "")
            suggestion = issue.get("suggestion", "")

            body = f"**AICR 评审** ({severity}/{category})\n\n{message}"
            if suggestion:
                body += f"\n\n**建议**: {suggestion}"

            ok = self.publisher.publish_issue(
                project_id=ctx.project_id,
                mr_iid=ctx.mr_iid,
                body=body,
                file_path=file_path,
                line=line,
                diff_refs=ctx.diff_refs,
                category=category,
                session=gl_session,
            )
            all_ok = all_ok and ok

        ok = self.publisher.publish_summary(
            project_id=ctx.project_id,
            mr_iid=ctx.mr_iid,
            score=score,
            summary=summary,
            issue_count=len(issues),
            threshold=SCORE_THRESHOLD,
            session=gl_session,
        )
        return all_ok and ok

    @staticmethod
    def _files_summary(files: list) -> str:
        lines = []
        for f in files:
            path = f.get("new_path") or f.get("old_path") or "?"
            lines.append(f"- `{path}`")
        return "\n".join(lines)

    @staticmethod
    def _build_diff_text(files: list, deleted_files: list | None = None) -> str:
        parts = []
        if deleted_files:
            lines = "\n".join(f"- `{p}`" for p in deleted_files)
            parts.append(f"## Deleted files (no patch hunks)\n{lines}")
        for f in files:
            path = f.get("new_path") or f.get("old_path") or "?"
            header = f"diff --git a/{path} b/{path}"
            diff_body = f.get("diff", "")
            content = f.get("content", "")
            section = header
            if diff_body:
                section += f"\n{diff_body}"
            if content:
                section += f"\n\n# Full file: {path}\n{content}"
            parts.append(section)
        return "\n\n".join(parts)

    @staticmethod
    def _build_code_quality(issues: list) -> list:
        return [
            {
                "description": issue.get("message", ""),
                "check_name": "aicr-review",
                "fingerprint": (
                    f"{issue.get('file', '')}:{issue.get('line', 0)}:"
                    f"{issue.get('category', '')}"
                ),
                "severity": issue.get("severity", "info"),
                "location": {
                    "path": issue.get("file", ""),
                    "lines": {"begin": issue.get("line", 0) or 1},
                },
            }
            for issue in issues
        ]

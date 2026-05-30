import logging
from typing import Dict, Any, List

from app.config import REVIEW_DRY_RUN, SCORE_THRESHOLD
from app.exceptions import LLMReviewError, NoReviewableChangesError
from app.gitlab.context_builder import ContextBuilder, MRContext
from app.gitlab.publisher import GitLabPublisher
from app.llm.base import LLMProvider
from app.review.chunker import DiffChunker
from app.review.prompt_renderer import PromptRenderer
from app.review.parser import StructuredResponseParser, ParseError
from app.utils.redact import redact_secrets

logger = logging.getLogger("aicr")


class ReviewOrchestrator:
    def __init__(
        self,
        context_builder: ContextBuilder,
        llm_provider: LLMProvider,
        publisher: GitLabPublisher,
    ):
        self.context_builder = context_builder
        self.llm = llm_provider
        self.publisher = publisher
        self.chunker = DiffChunker()
        self.renderer = PromptRenderer()
        self.parser = StructuredResponseParser()

    def run(self, project_id: int, mr_iid: int, extra_diff: str = "") -> Dict[str, Any]:
        logger.info(f"Starting review for project={project_id} MR !{mr_iid}")

        ctx: MRContext = self.context_builder.build(project_id, mr_iid, extra_diff)
        chunks = self.chunker.chunk_files(ctx.changed_files)

        if not chunks:
            raise NoReviewableChangesError(
                "No reviewable file changes in MR (supported extensions only)"
            )

        all_issues: list = []
        min_score = 100.0
        all_summaries: list = []
        llm_failures: list = []

        for i, chunk in enumerate(chunks):
            logger.info(f"Reviewing chunk {i + 1}/{len(chunks)} ({chunk['total_chars']} chars)")
            try:
                chunk_result = self._review_chunk(ctx, chunk, chunk_index=i, total_chunks=len(chunks))
            except LLMReviewError as e:
                llm_failures.append(str(e))
                continue

            all_issues.extend(chunk_result.get("issues", []))
            chunk_score = chunk_result.get("score", 100.0)
            min_score = min(min_score, chunk_score)
            if chunk_result.get("summary"):
                all_summaries.append(chunk_result["summary"])

        # 所有分块均 LLM 失败 → 503；部分失败则继续用已成功块的结果
        if llm_failures and len(llm_failures) == len(chunks):
            raise LLMReviewError("; ".join(llm_failures))

        if llm_failures:
            all_summaries.append(f"Partial LLM failures: {'; '.join(llm_failures)}")

        final_score = min_score
        summary = " | ".join(all_summaries) if all_summaries else "Review completed."

        if not REVIEW_DRY_RUN:
            self._publish_results(ctx, final_score, summary, all_issues)

        logger.info(f"Review complete: score={final_score}, issues={len(all_issues)}")
        return {
            "score": final_score,
            "summary": summary,
            "issues": all_issues,
            "code_quality": self._build_code_quality(all_issues),
        }

    def _review_chunk(
        self, ctx: MRContext, chunk: Dict, chunk_index: int = 0, total_chunks: int = 1
    ) -> Dict[str, Any]:
        system_prompt = self.renderer.render_system(
            context_md=ctx.context_md,
            language_hint="Java/Spring",
        )

        changed_files_summary = self._files_summary(chunk["files"])
        diff_text = redact_secrets(self._build_diff_text(chunk["files"]))

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

    def _publish_results(self, ctx: MRContext, score: float, summary: str, issues: list):
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

            self.publisher.publish_issue(
                project_id=ctx.project_id,
                mr_iid=ctx.mr_iid,
                body=body,
                file_path=file_path,
                line=line,
                diff_refs=ctx.diff_refs,
                category=category,
            )

        self.publisher.publish_summary(
            project_id=ctx.project_id,
            mr_iid=ctx.mr_iid,
            score=score,
            summary=summary,
            issue_count=len(issues),
            threshold=SCORE_THRESHOLD,
        )

    @staticmethod
    def _files_summary(files: list) -> str:
        lines = []
        for f in files:
            path = f.get("new_path") or f.get("old_path") or "?"
            lines.append(f"- `{path}`")
        return "\n".join(lines)

    @staticmethod
    def _build_diff_text(files: list) -> str:
        parts = []
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

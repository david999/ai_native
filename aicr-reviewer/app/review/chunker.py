"""将 MR 变更文件按 token 预算切分为多个 LLM 请求块。"""

import logging
from typing import List, Dict, Tuple

from app.config import REVIEW_MAX_INPUT_TOKENS
from app.review.language_priority import sort_by_language_priority
from app.review.token_utils import count_tokens

logger = logging.getLogger("aicr")


class DiffChunker:
    """按 REVIEW_MAX_INPUT_TOKENS 将 supported 文件打包成多块；单文件超大时优先压缩删除行，其次才截断。"""

    def chunk_files(self, changed_files: List[Dict]) -> List[Dict]:
        supported = [f for f in changed_files if f.get("is_supported")]
        ordered = sort_by_language_priority(supported)
        max_tokens = REVIEW_MAX_INPUT_TOKENS

        chunks: List[Dict] = []
        current_files: List[Dict] = []
        current_tokens = 0

        for f in ordered:
            file_entry, file_tokens = self._prepare_file(f, max_tokens)

            if current_tokens + file_tokens > max_tokens and current_files:
                chunks.append({
                    "files": current_files,
                    "total_chars": self._total_chars(current_files),
                    "total_tokens": current_tokens,
                })
                current_files = []
                current_tokens = 0

            current_files.append(file_entry)
            current_tokens += file_tokens

        if current_files:
            chunks.append({
                "files": current_files,
                "total_chars": self._total_chars(current_files),
                "total_tokens": current_tokens,
            })

        logger.info(
            f"Split {len(changed_files)} files into {len(chunks)} chunk(s) "
            f"(token budget={max_tokens})"
        )
        return chunks

    def _prepare_file(self, f: Dict, max_tokens: int) -> Tuple[Dict, int]:
        """准备单文件条目并返回 (entry, token_count)。

        超预算时优先顺序：
        1. 移除 diff 中的纯删除 hunk（保留新增/上下文行）
        2. 删除全文内容（content 字段）
        3. 字符截断（最后手段，对齐到 hunk 边界）
        """
        file_text = self._file_text(f)
        file_tokens = count_tokens(file_text)
        if file_tokens <= max_tokens:
            return f, file_tokens

        path = f.get("new_path") or f.get("old_path") or "?"

        # 第一步：移除 diff 中的纯删除 hunk
        stripped_diff = self._strip_deletion_hunks(f.get("diff") or "")
        entry_no_del = {**f, "diff": stripped_diff}
        tokens_no_del = count_tokens(self._file_text(entry_no_del))
        if tokens_no_del <= max_tokens:
            logger.info(
                f"Compressed {path} by removing deletion-only hunks: "
                f"~{file_tokens} -> ~{tokens_no_del} tokens"
            )
            return entry_no_del, tokens_no_del

        # 第二步：删除全文内容
        entry_no_content = {**entry_no_del, "content": ""}
        tokens_no_content = count_tokens(self._file_text(entry_no_content))
        if tokens_no_content <= max_tokens:
            logger.info(
                f"Compressed {path} by dropping full-file content: "
                f"~{file_tokens} -> ~{tokens_no_content} tokens"
            )
            return entry_no_content, tokens_no_content

        # 第三步：字符截断（最后手段）——对齐到 hunk 边界避免切断在 hunk 内部
        logger.warning(
            f"Truncating {path} from ~{tokens_no_content} to ~{max_tokens} tokens "
            f"(fallback after compression)"
        )
        diff_text = entry_no_content.get("diff") or ""
        base_text = self._file_text(entry_no_content)
        ratio = max_tokens / max(tokens_no_content, 1)
        max_chars = max(500, int(len(base_text) * ratio * 0.95))
        truncated_diff = self._truncate_at_hunk_boundary(diff_text, max_chars)
        entry_truncated = {
            **entry_no_content,
            "diff": truncated_diff + "\n... [truncated for token budget]",
        }
        return entry_truncated, count_tokens(self._file_text(entry_truncated))

    @staticmethod
    def _strip_deletion_hunks(diff: str) -> str:
        """移除 unified diff 中纯删除的 hunk（无 + 行的 hunk），保留包含新增行的 hunk。"""
        if not diff.strip():
            return diff
        lines = diff.splitlines(keepends=True)
        out: List[str] = []
        i = 0
        while i < len(lines):
            line = lines[i]
            if not line.startswith("@@"):
                out.append(line)
                i += 1
                continue
            # 收集该 hunk
            hunk: List[str] = [line]
            i += 1
            while i < len(lines) and not lines[i].startswith("@@"):
                hunk.append(lines[i])
                i += 1
            # 仅当 hunk 中有新增行时才保留
            has_addition = any(
                hl.startswith("+") and not hl.startswith("+++ ")
                for hl in hunk
            )
            if has_addition:
                out.extend(hunk)
        return "".join(out)

    @staticmethod
    def _truncate_at_hunk_boundary(diff: str, max_chars: int) -> str:
        """截断到最近 hunk 边界，避免切断在 hunk 内部。"""
        if len(diff) <= max_chars:
            return diff
        truncated = diff[:max_chars]
        last_hunk = truncated.rfind("\n@@")
        if last_hunk > 0:
            return truncated[:last_hunk]
        return truncated

    @staticmethod
    def _file_text(f: Dict) -> str:
        parts = [f"--- {f.get('old_path', '')}", f"+++ {f.get('new_path', '')}"]
        if f.get("diff"):
            parts.append(f["diff"])
        if f.get("content"):
            parts.append(f"\n# Full file content:\n{f['content']}")
        return "\n".join(parts)

    @staticmethod
    def _total_chars(files: List[Dict]) -> int:
        return sum(len(DiffChunker._file_text(f)) for f in files)

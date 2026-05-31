"""将 MR 变更文件按 token 预算切分为多个 LLM 请求块。"""

import logging
from typing import List, Dict, Tuple

from app.config import REVIEW_MAX_INPUT_TOKENS
from app.review.language_priority import sort_by_language_priority
from app.review.token_utils import count_tokens

logger = logging.getLogger("aicr")


class DiffChunker:
    """按 REVIEW_MAX_INPUT_TOKENS 将 supported 文件打包成多块；单文件超大时截断 diff。"""

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
        """准备单文件条目并返回 (entry, token_count)，每文件只 tokenize 一次。"""
        file_text = self._file_text(f)
        file_tokens = count_tokens(file_text)
        if file_tokens <= max_tokens:
            return f, file_tokens

        path = f.get("new_path") or f.get("old_path") or "?"
        logger.warning(
            f"Truncating {path} from ~{file_tokens} to ~{max_tokens} tokens"
        )
        ratio = max_tokens / max(file_tokens, 1)
        max_chars = max(500, int(len(file_text) * ratio * 0.95))
        truncated_diff = (f.get("diff") or "")[:max_chars]
        entry = {
            **f,
            "diff": truncated_diff + "\n... [truncated for token budget]",
            "content": "",
        }
        return entry, count_tokens(self._file_text(entry))

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

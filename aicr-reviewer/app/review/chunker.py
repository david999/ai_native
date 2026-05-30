"""将 MR 变更文件按 token 预算切分为多个 LLM 请求块。"""

import logging
from typing import List, Dict

from app.config import REVIEW_MAX_INPUT_TOKENS

logger = logging.getLogger("aicr")

# 粗略估算：1 token ≈ 4 字符（中英文混合场景下的保守值）
APPROX_CHARS_PER_TOKEN = 4


class DiffChunker:
    """按 REVIEW_MAX_INPUT_TOKENS 将 supported 文件打包成多块，单文件超大时截断 diff。"""

    def chunk_files(self, changed_files: List[Dict]) -> List[Dict]:
        max_chars = REVIEW_MAX_INPUT_TOKENS * APPROX_CHARS_PER_TOKEN
        chunks: List[Dict] = []
        current_files: List[Dict] = []
        current_chars = 0

        for f in changed_files:
            if not f.get("is_supported"):
                continue

            file_entry = self._maybe_truncate_file(f, max_chars)
            file_text = self._file_text(file_entry)
            file_chars = len(file_text)

            if current_chars + file_chars > max_chars and current_files:
                chunks.append({"files": current_files, "total_chars": current_chars})
                current_files = []
                current_chars = 0

            current_files.append(file_entry)
            current_chars += file_chars

        if current_files:
            chunks.append({"files": current_files, "total_chars": current_chars})

        logger.info(
            f"Split {len(changed_files)} files into {len(chunks)} chunk(s)"
        )
        return chunks

    @staticmethod
    def _maybe_truncate_file(f: Dict, max_chars: int) -> Dict:
        file_text = DiffChunker._file_text(f)
        if len(file_text) <= max_chars:
            return f
        logger.warning(
            f"Truncating {f.get('new_path', '?')} from {len(file_text)} to {max_chars} chars"
        )
        truncated_diff = (f.get("diff") or "")[:max_chars]
        return {
            **f,
            "diff": truncated_diff + "\n... [truncated for token budget]",
            "content": "",
        }

    @staticmethod
    def _file_text(f: Dict) -> str:
        parts = [f"--- {f.get('old_path', '')}", f"+++ {f.get('new_path', '')}"]
        if f.get("diff"):
            parts.append(f["diff"])
        if f.get("content"):
            parts.append(f"\n# Full file content:\n{f['content']}")
        return "\n".join(parts)

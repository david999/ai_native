import logging
from typing import List, Dict

from app.config import REVIEW_MAX_INPUT_TOKENS

logger = logging.getLogger("aicr")

APPROX_CHARS_PER_TOKEN = 4


class DiffChunker:
    def chunk_files(self, changed_files: List[Dict]) -> List[Dict]:
        max_chars = REVIEW_MAX_INPUT_TOKENS * APPROX_CHARS_PER_TOKEN
        chunks: List[Dict] = []
        current_files: List[Dict] = []
        current_chars = 0

        for f in changed_files:
            if not f.get("is_supported"):
                continue

            file_text = self._file_text(f)
            file_chars = len(file_text)

            if file_chars > max_chars and current_files:
                chunks.append({"files": current_files, "total_chars": current_chars})
                current_files = []
                current_chars = 0

            if current_chars + file_chars > max_chars and current_files:
                chunks.append({"files": current_files, "total_chars": current_chars})
                current_files = []
                current_chars = 0

            current_files.append(f)
            current_chars += file_chars

        if current_files:
            chunks.append({"files": current_files, "total_chars": current_chars})

        logger.info(f"Split {len(changed_files)} files into {len(chunks)} chunk(s)")
        return chunks

    @staticmethod
    def _file_text(f: Dict) -> str:
        parts = [f"--- {f.get('old_path', '')}", f"+++ {f.get('new_path', '')}"]
        if f.get("diff"):
            parts.append(f["diff"])
        if f.get("content"):
            parts.append(f"\n# Full file content:\n{f['content']}")
        return "\n".join(parts)

"""PR diff 压缩：合并纯删除文件列表，并剔除 deletion-only hunks（对齐 pr-agent 思路）。"""

from __future__ import annotations

import re
from typing import List, Tuple

_DELETED_FILE_MARKER = re.compile(r"^deleted file mode \d+", re.MULTILINE)


def _hunk_is_deletion_only(hunk_lines: List[str]) -> bool:
    """Hunk 内无新增行（+）则视为仅删除。"""
    for line in hunk_lines:
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("@@"):
            continue
        if line.startswith("+") and not line.startswith("+++"):
            return False
    return True


def compress_unified_diff(diff: str) -> str:
    """移除 unified diff 中仅含删除的 hunk，保留有新增/修改的 hunk。"""
    if not diff or not diff.strip():
        return ""

    lines = diff.splitlines()
    out: List[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("@@"):
            out.append(line)
            i += 1
            continue

        hunk_start = i
        i += 1
        while i < len(lines) and not lines[i].startswith("@@"):
            i += 1
        hunk = lines[hunk_start:i]
        if not _hunk_is_deletion_only(hunk):
            out.extend(hunk)

    return "\n".join(out) + ("\n" if diff.endswith("\n") else "")


def is_entire_file_deletion(change: dict) -> bool:
    if change.get("deleted_file"):
        return True
    diff = change.get("diff") or ""
    return bool(_DELETED_FILE_MARKER.search(diff))


def compress_change(change: dict) -> Tuple[dict | None, str | None]:
    """处理单文件变更。

    Returns:
        (file_entry, deleted_path): 若整文件删除则 file_entry 为 None，deleted_path 为路径。
    """
    old_path = change.get("old_path") or ""
    new_path = change.get("new_path") or ""
    path = new_path or old_path

    if is_entire_file_deletion(change):
        return None, path or old_path

    raw_diff = change.get("diff") or ""
    compressed = compress_unified_diff(raw_diff)
    if not compressed.strip() and raw_diff.strip():
        # 压缩后无有效 hunks（例如仅删除行）— 不送入 LLM
        return None, None

    return {**change, "diff": compressed}, None


def compress_changes(changes: List[dict]) -> Tuple[List[dict], List[str]]:
    """批量压缩 MR/compare 变更列表。"""
    files: List[dict] = []
    deleted: List[str] = []

    for change in changes:
        entry, deleted_path = compress_change(change)
        if deleted_path:
            deleted.append(deleted_path)
        elif entry is not None:
            files.append(entry)

    return files, deleted

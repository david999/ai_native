"""从 unified diff 解析新文件行号范围，用于过滤 LLM issue（仅保留 diff hunk 内）。"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

LineRange = Tuple[int, int]


def _normalize_path(path: str) -> str:
    return (path or "").replace("\\", "/").lstrip("./")


def parse_diff_new_line_ranges(diff: str) -> List[LineRange]:
    """解析 diff 中属于新文件侧的行号区间（含 hunk 内 context 与新增行）。"""
    if not diff or not diff.strip():
        return []

    ranges: List[LineRange] = []
    new_line = 0
    hunk_start = 0
    hunk_end = 0
    in_hunk = False

    for raw in diff.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("@@"):
            if in_hunk and hunk_end >= hunk_start:
                ranges.append((hunk_start, hunk_end))
            m = _HUNK_HEADER.match(line)
            if not m:
                in_hunk = False
                continue
            new_line = int(m.group(1))
            in_hunk = True
            hunk_start = new_line
            hunk_end = new_line - 1
            continue

        if not in_hunk:
            continue

        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+") or line.startswith(" "):
            hunk_end = new_line
            new_line += 1
        # deletion-only lines in hunk do not advance new file line

    if in_hunk and hunk_end >= hunk_start:
        ranges.append((hunk_start, hunk_end))

    return _merge_ranges(ranges)


def _merge_ranges(ranges: List[LineRange]) -> List[LineRange]:
    if not ranges:
        return []
    sorted_ranges = sorted(ranges)
    merged: List[LineRange] = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def build_diff_line_index(changed_files: List[dict]) -> Dict[str, List[LineRange]]:
    """path -> 新文件行号区间列表。"""
    index: Dict[str, List[LineRange]] = {}
    for f in changed_files:
        path = f.get("new_path") or f.get("old_path") or ""
        if not path or path.startswith("_aicr") or path.startswith("_ci_"):
            continue
        diff = f.get("diff") or ""
        ranges = parse_diff_new_line_ranges(diff)
        if ranges:
            key = _normalize_path(path)
            if key in index:
                index[key] = _merge_ranges(index[key] + ranges)
            else:
                index[key] = ranges
    return index


def line_in_diff(line: int, ranges: List[LineRange]) -> bool:
    if line <= 0 or not ranges:
        return False
    return any(start <= line <= end for start, end in ranges)


def filter_issues_to_diff(
    issues: List[dict],
    changed_files: List[dict],
    *,
    allow_placeholder_paths: bool = True,
) -> Tuple[List[dict], List[dict]]:
    """返回 (kept, dropped)。"""
    index = build_diff_line_index(changed_files)
    kept: List[dict] = []
    dropped: List[dict] = []

    for issue in issues:
        path = _normalize_path(str(issue.get("file", "")))
        line = int(issue.get("line") or 0)

        if allow_placeholder_paths and path.startswith("_aicr"):
            kept.append(issue)
            continue

        if not path:
            dropped.append(issue)
            continue

        ranges = index.get(path)
        if ranges is None:
            # 尝试后缀匹配（模型有时省略目录）
            for key, rs in index.items():
                if key.endswith(path) or path.endswith(key):
                    ranges = rs
                    break

        if ranges and line_in_diff(line, ranges):
            kept.append(issue)
        else:
            dropped.append(issue)

    return kept, dropped

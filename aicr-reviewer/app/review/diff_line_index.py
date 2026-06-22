"""从 unified diff 解析新文件行号范围，用于过滤 LLM issue（仅保留 diff hunk 内）。"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Set, Tuple

from app.review.parser import StructuredResponseParser

_HUNK_HEADER = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")

LineRange = Tuple[int, int]


def _normalize_path(path: str) -> str:
    return (path or "").replace("\\", "/").lstrip("./")


def paths_match(index_path: str, issue_path: str) -> bool:
    """严格路径匹配：相等或一方为另一方的仓库相对子路径。"""
    a = _normalize_path(index_path)
    b = _normalize_path(issue_path)
    if not a or not b:
        return False
    if a == b:
        return True
    return a.endswith("/" + b) or b.endswith("/" + a)


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


def _lookup_ranges(index: Dict[str, List[LineRange]], issue_path: str) -> Optional[List[LineRange]]:
    if issue_path in index:
        return index[issue_path]
    for key, rs in index.items():
        if paths_match(key, issue_path):
            return rs
    return None


def filter_issues_to_diff(
    issues: List[dict],
    changed_files: List[dict],
    *,
    allow_placeholder_paths: bool = True,
    additional_allowed_paths: Optional[List[str]] = None,
) -> Tuple[List[dict], List[dict]]:
    """返回 (kept, dropped)。"""
    index = build_diff_line_index(changed_files)
    allowed_paths: Set[str] = {
        _normalize_path(p) for p in (additional_allowed_paths or []) if p
    }
    kept: List[dict] = []
    dropped: List[dict] = []

    for issue in issues:
        path = _normalize_path(str(issue.get("file", "")))
        line = StructuredResponseParser._safe_line(issue.get("line"))

        if allow_placeholder_paths and path.startswith("_aicr"):
            kept.append(issue)
            continue

        if path in allowed_paths:
            kept.append(issue)
            continue

        if not path:
            dropped.append(issue)
            continue

        ranges = _lookup_ranges(index, path)
        if ranges and line_in_diff(line, ranges):
            kept.append(issue)
        else:
            dropped.append(issue)

    return kept, dropped


def resolve_line_by_existing_code(
    existing_code: str,
    changed_files: List[dict],
    issue_path: str,
) -> Optional[int]:
    """通过 existing_code 文本匹配在 diff hunk 中精确定位行号。

    策略：
    1. 在对应文件的 diff 中逐行搜索 existing_code 的第一行（去除 +/- 前缀）。
    2. 找到后返回该行的新文件行号。
    3. 匹配失败时返回 None（调用方可降级使用 LLM 输出的原始行号）。
    """
    if not existing_code or not existing_code.strip():
        return None

    # 取 existing_code 的第一行作为锚点搜索
    first_line = existing_code.splitlines()[0].strip()
    if not first_line:
        return None

    norm_path = _normalize_path(issue_path)
    target_file: Optional[dict] = None
    for f in changed_files:
        candidate = _normalize_path(f.get("new_path") or f.get("old_path") or "")
        if paths_match(candidate, norm_path):
            target_file = f
            break

    if target_file is None:
        return None

    diff = target_file.get("diff") or ""
    if not diff.strip():
        return None

    # 遍历 diff 行，跟踪新文件行号，寻找 existing_code 首行
    new_line = 0
    in_hunk = False
    for raw in diff.splitlines():
        if raw.startswith("@@"):
            m = _HUNK_HEADER.match(raw)
            if m:
                new_line = int(m.group(1))
                in_hunk = True
            continue
        if not in_hunk:
            continue
        if raw.startswith("---") or raw.startswith("+++"):
            continue
        if raw.startswith("-"):
            # 删除行不计入新文件行号
            continue
        # 上下文行（空格开头）或新增行（+开头）
        code_line = raw[1:] if raw.startswith("+") or raw.startswith(" ") else raw
        if code_line.strip() == first_line:
            return new_line
        if raw.startswith("+") or raw.startswith(" "):
            new_line += 1

    return None

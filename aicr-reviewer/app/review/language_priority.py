"""按 MR 内语言/扩展名出现频率对变更文件排序（主语言优先进入 prompt）。"""

from __future__ import annotations

from collections import Counter
from typing import Dict, List


def _path_key(file_entry: Dict) -> str:
    return file_entry.get("new_path") or file_entry.get("old_path") or ""


def _extension(path: str) -> str:
    if not path:
        return ""
    lower = path.lower()
    if "/" in lower:
        base = lower.rsplit("/", 1)[-1]
    else:
        base = lower
    if "." in base:
        return base[base.rfind(".") :]
    return base


def sort_by_language_priority(files: List[Dict]) -> List[Dict]:
    """同扩展名文件越多，排序越靠前；同优先级按路径稳定排序。"""
    ext_counts: Counter[str] = Counter()
    for f in files:
        ext_counts[_extension(_path_key(f))] += 1

    def sort_key(f: Dict) -> tuple:
        path = _path_key(f)
        ext = _extension(path)
        return (-ext_counts[ext], path)

    return sorted(files, key=sort_key)


def infer_language_hint(files: List[Dict]) -> str:
    """根据变更文件扩展名推断提示词语言标签。"""
    ext_counts: Counter[str] = Counter()
    for f in files:
        ext_counts[_extension(_path_key(f))] += 1

    if not ext_counts:
        return "General"

    top_ext, _ = ext_counts.most_common(1)[0]
    mapping = {
        ".java": "Java/Spring",
        ".kt": "Kotlin",
        ".py": "Python",
        ".go": "Go",
        ".js": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript/React",
        ".rs": "Rust",
        ".sql": "SQL",
        ".xml": "XML/Spring",
        ".yml": "YAML",
        ".yaml": "YAML",
        ".properties": "Java Properties",
        ".gradle": "Gradle",
    }
    return mapping.get(top_ext, f"{top_ext.lstrip('.') or 'General'}")

"""从 MRContext 组装供 LLM 使用的 diff 文本。"""

from __future__ import annotations

from app.config import REVIEW_MAX_INPUT_TOKENS
from app.gitlab.context_builder import MRContext

_APPROX_CHARS_PER_TOKEN = 4
_DEFAULT_TOOL_MAX_CHARS = REVIEW_MAX_INPUT_TOKENS * _APPROX_CHARS_PER_TOKEN


def build_diff_text_from_context(
    ctx: MRContext, *, max_chars: int | None = None
) -> str:
    if max_chars is None:
        max_chars = _DEFAULT_TOOL_MAX_CHARS
    parts = []
    if ctx.deleted_files:
        lines = "\n".join(f"- `{p}`" for p in ctx.deleted_files)
        parts.append(f"## Deleted files (no patch hunks)\n{lines}")

    for f in ctx.changed_files:
        if not f.get("is_supported", True):
            continue
        path = f.get("new_path") or f.get("old_path") or "?"
        header = f"diff --git a/{path} b/{path}"
        section = header
        diff_body = f.get("diff", "")
        if diff_body:
            section += f"\n{diff_body}"
        content = f.get("content", "")
        if content:
            section += f"\n\n# Full file: {path}\n{content}"
        parts.append(section)

    text = "\n\n".join(parts)
    if max_chars and len(text) > max_chars:
        text = text[:max_chars] + "\n\n... (truncated)"
    return text


def changed_files_summary(ctx: MRContext) -> str:
    lines = []
    for f in ctx.changed_files:
        if not f.get("is_supported", True):
            continue
        path = f.get("new_path") or f.get("old_path") or "?"
        lines.append(f"- `{path}`")
    if ctx.deleted_files:
        for p in ctx.deleted_files:
            lines.append(f"- `{p}` (deleted)")
    return "\n".join(lines) if lines else "(no supported file changes)"

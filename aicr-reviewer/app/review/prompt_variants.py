"""提示词变体（variants/）解析与校验。"""

from __future__ import annotations

import hashlib
import logging
import re
from functools import lru_cache
from pathlib import Path

import yaml

from app.config import AICR_SYSTEM_TEMPLATE
from app.exceptions import InvalidTemplateError
from app.review.language_priority import resolve_system_template

logger = logging.getLogger("aicr")

_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"
_VARIANTS_DIR = _PROMPTS_DIR / "variants"
_VARIANTS_MANIFEST = _VARIANTS_DIR / "manifest.yaml"
_SAFE_SEGMENT = re.compile(r"^[a-zA-Z0-9_.-]+$")


@lru_cache(maxsize=1)
def _allowed_template_paths() -> frozenset[str]:
    """允许加载的模板路径（相对 prompts/）。"""
    allowed: set[str] = set()
    for path in _PROMPTS_DIR.glob("system_*.j2"):
        allowed.add(path.name)
    if _VARIANTS_MANIFEST.is_file():
        data = yaml.safe_load(_VARIANTS_MANIFEST.read_text(encoding="utf-8")) or {}
        for item in data.get("variants", []):
            file_path = (item.get("file") or "").strip()
            if file_path and _is_safe_relative_template(file_path):
                allowed.add(file_path.replace("\\", "/"))
            vid = (item.get("id") or "").strip()
            if vid:
                allowed.add(vid)
    return frozenset(allowed)


def _is_safe_relative_template(path: str) -> bool:
    if not path or ".." in path or path.startswith("/") or path.startswith("\\"):
        return False
    parts = path.replace("\\", "/").split("/")
    return all(_SAFE_SEGMENT.match(p) for p in parts if p)


def _file_for_allowed_key(key: str) -> str | None:
    """将 id 或相对路径解析为 prompts/ 下的模板文件路径（须在 allowlist 内）。"""
    key = (key or "").strip()
    if not key or ".." in key:
        return None
    allowed = _allowed_template_paths()
    if key in allowed and not key.endswith(".j2"):
        candidate = f"variants/{key}.j2"
        if (_PROMPTS_DIR / candidate).is_file():
            return candidate
    if key.endswith(".j2") and key in allowed and _is_safe_relative_template(key):
        path = _PROMPTS_DIR / key
        if path.is_file():
            return key.replace("\\", "/")
    return None


def normalize_template_override(name: str | None) -> str | None:
    """将 override 规范为 allowlist 内的 Jinja2 模板路径。"""
    if not name or not str(name).strip():
        return None
    return _file_for_allowed_key(str(name).strip())


def validate_strict_template_override(override: str | None) -> None:
    """显式 override 不在白名单时抛 InvalidTemplateError（供 API 在编排前校验）。"""
    key = (override or "").strip()
    if not key:
        return
    if not normalize_template_override(key):
        raise InvalidTemplateError(f"Unknown or disallowed system_template: {key}")


def resolve_effective_system_template(
    language_hint: str,
    *,
    override: str | None = None,
    strict_override: bool = False,
) -> str:
    """返回相对 prompts/ 的模板路径。

    strict_override=True 时，显式 override 不在 allowlist 则抛 InvalidTemplateError。
    """
    override_key = (override or "").strip()
    if override_key:
        resolved = normalize_template_override(override_key)
        if resolved:
            return resolved
        if strict_override:
            raise InvalidTemplateError(
                f"Unknown or disallowed system_template: {override_key}"
            )

    if AICR_SYSTEM_TEMPLATE:
        env_resolved = normalize_template_override(AICR_SYSTEM_TEMPLATE)
        if env_resolved:
            return env_resolved
        logger.warning(
            "Ignoring invalid AICR_SYSTEM_TEMPLATE=%r (not in allowlist)",
            AICR_SYSTEM_TEMPLATE,
        )

    return resolve_system_template(language_hint)


def prompt_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

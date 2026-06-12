"""Monorepo 环境变量加载：操作系统环境变量优先，evn/.env 仅回填缺省。"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE_PATHS = (
    _REPO_ROOT / "evn" / ".env",
    _REPO_ROOT / ".env",
    Path(__file__).resolve().parents[1] / ".env",
)

# 这些键优先使用 Process / User / Machine 环境变量，.env 中同键仅作缺省
_OS_PRIORITY_KEYS = frozenset({
    "LLM_API_KEY",
    "LLM_MODEL",
    "LLM_PROVIDER",
    "LLM_API_BASE",
    "LLM_TIMEOUT_SECONDS",
    "LLM_MAX_TOKENS",
    "LLM_TEMPERATURE",
    "AICR_BOT_TOKEN",
    "GITLAB_URL",
    "ROOT_PAT",
    "REVIEW_API_SECRET",
    "REVIEW_API_ALLOW_INSECURE",
    "GITLAB_START_COMMAND",
})


def _windows_env(name: str, scope: str) -> str:
    if sys.platform != "win32":
        return ""
    try:
        r = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"[Environment]::GetEnvironmentVariable('{name}','{scope}')",
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        return (r.stdout or "").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def os_env_first(name: str) -> str:
    """Process → User → Machine，返回首个非空值。"""
    val = os.environ.get(name, "").strip()
    if val:
        return val
    if sys.platform == "win32":
        for scope in ("User", "Machine"):
            val = _windows_env(name, scope)
            if val:
                return val
    return ""


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if key:
            out[key] = value.strip()
    return out


def apply_monorepo_env(*, include_all_file_keys: bool = True) -> None:
    """应用 monorepo 环境变量到 ``os.environ``。

    规则：
    1. 对 ``_OS_PRIORITY_KEYS``：OS 环境变量非空则优先，否则用 .env 非空值。
    2. 其余 .env 键：仅当 ``os.environ`` 中尚未设置时写入（setdefault）。
    """
    file_vars: dict[str, str] = {}
    for path in _ENV_FILE_PATHS:
        for key, value in _parse_env_file(path).items():
            file_vars.setdefault(key, value)

    for key in _OS_PRIORITY_KEYS:
        os_val = os_env_first(key)
        if os_val:
            os.environ[key] = os_val
        elif file_vars.get(key):
            os.environ.setdefault(key, file_vars[key])

    if include_all_file_keys:
        for key, value in file_vars.items():
            if key in _OS_PRIORITY_KEYS or not value:
                continue
            os.environ.setdefault(key, value)

"""~/.opencodereview/config.json 共享读取（OCR CI 扩展字段）。

供 scripts/acceptance/bake_ocr_config.py 与 post_ocr_to_gitlab.py 使用。

OCR 官方仅文档化 llm.*；本仓库在同一文件中扩展 gitlab.api_token，免 CI Variable。

逻辑清单：
- config_search_paths()：OCR_CONFIG_PATH → /root/.opencodereview → 用户目录
- resolve_gitlab_api_token()：首个可读配置生效
- 不做：合并多个配置文件；校验 LLM 密钥
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def user_config_path() -> Path:
    """返回当前 OS 下 OCR CLI 默认 config.json 路径。"""
    return Path.home() / ".opencodereview" / "config.json"


def config_search_paths() -> list[Path]:
    """解析 gitlab.api_token 的搜索路径（先命中者优先）。

    OCR_CONFIG_PATH：显式覆盖（测试/本地调试）
    /root/.opencodereview/config.json：ocr-ci Docker 镜像内 bake 路径
    user_config_path()：开发机 CLI 配置
    """
    paths: list[Path] = []
    env_path = os.environ.get("OCR_CONFIG_PATH", "").strip()
    if env_path:
        paths.append(Path(env_path))
    paths.append(Path("/root/.opencodereview/config.json"))
    paths.append(user_config_path())
    return paths


def load_config_file(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def gitlab_api_token_from_config(data: dict[str, Any]) -> str:
    """从 bake 配置提取 GitLab PAT（gitlab.api_token 或旧字段）。"""
    gitlab = data.get("gitlab")
    if isinstance(gitlab, dict):
        token = gitlab.get("api_token") or gitlab.get("auth_token") or ""
        if token:
            return str(token)
    legacy = data.get("gitlab_api_token")
    return str(legacy) if legacy else ""


def resolve_gitlab_api_token() -> str:
    """GITLAB_API_TOKEN 未设置时，为 post_ocr_to_gitlab.py 解析 token。"""
    for path in config_search_paths():
        data = load_config_file(path)
        if not data:
            continue
        token = gitlab_api_token_from_config(data)
        if token:
            return token
    return ""

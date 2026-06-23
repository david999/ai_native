"""Shared helpers for ~/.opencodereview/config.json (OCR CI extension fields).

Used by bake_ocr_config.py, post_ocr_to_gitlab.py, and verify_local_ocr.py.

OCR upstream only documents llm.* in config.json; this repo extends the same file with
gitlab.api_token for GitLab MR posting without CI Variables.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


def user_config_path() -> Path:
    """Return the OCR CLI default config path on the current OS."""
    return Path.home() / ".opencodereview" / "config.json"


def config_search_paths() -> list[Path]:
    """Ordered paths for resolving gitlab.api_token (first hit wins).

    OCR_CONFIG_PATH: explicit override (tests / local debugging)
    /root/.opencodereview/config.json: baked into ocr-ci Docker image
    user_config_path(): developer machine CLI config
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
    """Extract GitLab PAT from baked config (gitlab.api_token or legacy keys)."""
    gitlab = data.get("gitlab")
    if isinstance(gitlab, dict):
        token = gitlab.get("api_token") or gitlab.get("auth_token") or ""
        if token:
            return str(token)
    legacy = data.get("gitlab_api_token")
    return str(legacy) if legacy else ""


def resolve_gitlab_api_token() -> str:
    """Resolve token for post_ocr_to_gitlab.py when GITLAB_API_TOKEN env is unset."""
    for path in config_search_paths():
        data = load_config_file(path)
        if not data:
            continue
        token = gitlab_api_token_from_config(data)
        if token:
            return token
    return ""

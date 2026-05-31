"""加载部署级与仓库级 ``.aicr/config.toml``，在环境变量未设置时提供默认值。"""

from __future__ import annotations

import logging
import os
import tomllib
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("aicr")

_MONOREPO_ROOT = Path(__file__).resolve().parents[2]


def _toml_path() -> Path:
    custom = os.getenv("AICR_CONFIG_PATH", "").strip()
    if custom:
        return Path(custom)
    return _MONOREPO_ROOT / "evn" / ".aicr" / "config.toml"


def load_deploy_config() -> Dict[str, Any]:
    path = _toml_path()
    if not path.is_file():
        return {}
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        logger.info(f"Loaded deploy config from {path}")
        return data
    except Exception as e:
        logger.warning(f"Failed to load {path}: {e}")
        return {}


def load_project_config_from_repo(project, mr) -> Dict[str, Any]:
    """从 MR 源/目标分支读取 ``.aicr/config.toml``（若存在）。"""
    for ref in (mr.source_branch, mr.target_branch):
        try:
            from app.gitlab.session import gitlab_call

            raw = gitlab_call(
                lambda r=ref: project.files.raw(
                    file_path=".aicr/config.toml", ref=r
                )
            )
            data = tomllib.loads(raw.decode("utf-8", errors="ignore"))
            logger.info(f"Loaded project .aicr/config.toml from ref={ref}")
            return data
        except Exception:
            continue
    return {}


def deep_get(data: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = data
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def merged_config(
    deploy: Optional[Dict[str, Any]] = None,
    project: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """浅合并：project 覆盖 deploy 的同名 section 键。"""
    base = dict(deploy or {})
    for section, values in (project or {}).items():
        if isinstance(values, dict) and isinstance(base.get(section), dict):
            merged_section = dict(base[section])
            merged_section.update(values)
            base[section] = merged_section
        else:
            base[section] = values
    return base


def toml_or_env_bool(env_name: str, toml_val: Any, default: bool) -> bool:
    if env_name in os.environ:
        return os.getenv(env_name, "0") == "1"
    if isinstance(toml_val, bool):
        return toml_val
    if isinstance(toml_val, str):
        return toml_val.lower() in ("1", "true", "yes", "on")
    return default


def toml_or_env_float(env_name: str, toml_val: Any, default: float) -> float:
    if env_name in os.environ:
        return float(os.getenv(env_name, str(default)))
    if toml_val is not None:
        return float(toml_val)
    return default


def toml_or_env_str(env_name: str, toml_val: Any, default: str) -> str:
    if env_name in os.environ:
        return os.getenv(env_name, default)
    if toml_val is not None:
        return str(toml_val)
    return default


def toml_or_env_triggers(env_name: str, toml_list: Any, default: List[str]) -> List[str]:
    if env_name in os.environ:
        raw = os.getenv(env_name, "")
        parts = [p.strip() for p in raw.split(",") if p.strip()]
        return parts or default
    if isinstance(toml_list, list):
        return [str(x) for x in toml_list if str(x).strip()]
    return default

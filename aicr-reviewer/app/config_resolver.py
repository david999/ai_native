"""按 MR 合并部署级与仓库级 config.toml（环境变量仍在 import 时优先）。"""

from __future__ import annotations

import os
from typing import Any, Dict, List

from app import config as app_config
from app.config_toml import deep_get, load_deploy_config, merged_config

_DEPLOY_CONFIG = load_deploy_config()


def merged_for_project(project_config: Dict[str, Any] | None) -> Dict[str, Any]:
    return merged_config(_DEPLOY_CONFIG, project_config or {})


def ask_triggers_for_project(project_config: Dict[str, Any] | None) -> List[str]:
    if "AICR_ASK_TRIGGERS" in os.environ:
        return list(app_config.AICR_ASK_TRIGGERS)
    merged = merged_for_project(project_config)
    triggers = deep_get(merged, "ask", "triggers")
    if isinstance(triggers, list) and triggers:
        return [str(t) for t in triggers if str(t).strip()]
    return list(app_config.AICR_ASK_TRIGGERS)


def bot_username_for_project(project_config: Dict[str, Any] | None) -> str:
    if "AICR_BOT_USERNAME" in os.environ:
        return app_config.AICR_BOT_USERNAME
    merged = merged_for_project(project_config)
    name = deep_get(merged, "ask", "bot_username")
    return str(name) if name else app_config.AICR_BOT_USERNAME


def llm_settings_for_tool(tool: str, project_config: Dict[str, Any] | None) -> Dict[str, Any]:
    """返回 ``model``、``temperature``；环境变量 ``LLM_MODEL_DESCRIBE`` 等优先于 TOML。"""
    tool_key = tool.strip().lower().replace("-", "_")
    env_model_key = f"LLM_MODEL_{tool_key.upper()}"
    env_temp_key = f"LLM_TEMPERATURE_{tool_key.upper()}"

    model = app_config.LLM_MODEL
    if env_model_key in os.environ:
        model = os.getenv(env_model_key, model) or model
    else:
        merged = merged_for_project(project_config)
        toml_model = deep_get(merged, "llm", tool_key, "model")
        if toml_model:
            model = str(toml_model)

    temperature = app_config.LLM_TEMPERATURE
    if env_temp_key in os.environ:
        temperature = float(os.getenv(env_temp_key, str(temperature)))
    else:
        merged = merged_for_project(project_config)
        toml_temp = deep_get(merged, "llm", tool_key, "temperature")
        if toml_temp is not None:
            temperature = float(toml_temp)

    return {"model": model, "temperature": temperature}


def suppress_review_after_describe(project_config: Dict[str, Any] | None) -> bool:
    if "AICR_SUPPRESS_REVIEW_AFTER_DESCRIBE" in os.environ:
        return os.getenv("AICR_SUPPRESS_REVIEW_AFTER_DESCRIBE", "1") == "1"
    merged = merged_for_project(project_config)
    val = deep_get(merged, "tools", "suppress_review_after_describe")
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("1", "true", "yes", "on")
    return app_config.AICR_SUPPRESS_REVIEW_AFTER_DESCRIBE

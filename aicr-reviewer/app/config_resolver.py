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

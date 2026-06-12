"""从 monorepo 环境文件加载配置。

加载顺序：

1. **操作系统环境变量**（Process / User / Machine）优先，尤其 ``LLM_API_KEY``、``LLM_MODEL`` 等
2. ``<repo>/evn/.env`` → ``<repo>/.env`` → ``aicr-reviewer/.env`` 仅回填缺省

所有模块应 ``from app.config import ...`` 读取常量，避免散落 ``os.getenv``。
"""

import os
from pathlib import Path

from app.env_loader import apply_monorepo_env

# aicr-reviewer/app/config.py -> parents[2] = 仓库根目录
_MONOREPO_ROOT = Path(__file__).resolve().parents[2]

apply_monorepo_env()

from app.config_toml import (  # noqa: E402
    deep_get,
    load_deploy_config,
    toml_or_env_bool,
    toml_or_env_float,
    toml_or_env_str,
    toml_or_env_triggers,
)

_DEPLOY_CONFIG = load_deploy_config()

GITLAB_URL = os.getenv("GITLAB_URL", "http://localhost:8000")
AICR_BOT_TOKEN = os.getenv("AICR_BOT_TOKEN", "")
SCORE_THRESHOLD = toml_or_env_float(
    "AICR_SCORE_THRESHOLD",
    deep_get(_DEPLOY_CONFIG, "review", "score_threshold"),
    60.0,
)
REVIEW_API_SECRET = os.getenv("REVIEW_API_SECRET", "")
REVIEW_API_ALLOW_INSECURE = os.getenv("REVIEW_API_ALLOW_INSECURE", "0") == "1"

GITLAB_TIMEOUT_SECONDS = int(os.getenv("GITLAB_TIMEOUT_SECONDS", "30"))
GITLAB_API_RETRIES = int(os.getenv("GITLAB_API_RETRIES", "3"))
REVIEW_MAX_CONCURRENT = int(os.getenv("REVIEW_MAX_CONCURRENT", "2"))

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ctyun_openai")
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://wishub-x6.ctyun.cn/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")
LLM_TIMEOUT_SECONDS = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))

REVIEW_MAX_INPUT_TOKENS = int(os.getenv("REVIEW_MAX_INPUT_TOKENS", "12000"))
CONTEXT_MAX_CHARS = int(os.getenv("CONTEXT_MAX_CHARS", "8000"))
REVIEW_DRY_RUN = os.getenv("REVIEW_DRY_RUN", "0") == "1"

# 阶段 A：token 估算、增量评审状态
REVIEW_USE_TIKTOKEN = os.getenv("REVIEW_USE_TIKTOKEN", "1") == "1"
TIKTOKEN_ENCODING = os.getenv("TIKTOKEN_ENCODING", "cl100k_base")
AICR_INCREMENTAL_REVIEW = os.getenv("AICR_INCREMENTAL_REVIEW", "1") == "1"
AICR_FORCE_FULL_REVIEW = os.getenv("AICR_FORCE_FULL_REVIEW", "0") == "1"
AICR_STATE_DIR = Path(
    os.getenv("AICR_STATE_DIR", str(_MONOREPO_ROOT / "evn" / ".aicr-state"))
)

# 阶段 B / P2：增量时不拉全文、并行 chunk、相同 SHA 跳过
AICR_FETCH_FULL_FILE = os.getenv("AICR_FETCH_FULL_FILE", "1") == "1"
AICR_FETCH_FULL_FILE_ON_INCREMENTAL = (
    os.getenv("AICR_FETCH_FULL_FILE_ON_INCREMENTAL", "0") == "1"
)
REVIEW_CHUNK_MAX_WORKERS = max(1, int(os.getenv("REVIEW_CHUNK_MAX_WORKERS", "2")))

# 提示词变体：强制指定 variants/*.j2 或标准 system_*.j2（空=按语言自动选择）
AICR_SYSTEM_TEMPLATE = os.getenv("AICR_SYSTEM_TEMPLATE", "").strip()

# 阶段 B：diff 内过滤、self-reflection、多语言 system 模板
AICR_FILTER_ISSUES_TO_DIFF = toml_or_env_bool(
    "AICR_FILTER_ISSUES_TO_DIFF",
    deep_get(_DEPLOY_CONFIG, "review", "filter_issues_to_diff"),
    True,
)
AICR_SELF_REFLECTION = toml_or_env_bool(
    "AICR_SELF_REFLECTION",
    deep_get(_DEPLOY_CONFIG, "review", "self_reflection"),
    True,
)
AICR_REFLECTION_SCORE_THRESHOLD = toml_or_env_float(
    "AICR_REFLECTION_SCORE_THRESHOLD",
    deep_get(_DEPLOY_CONFIG, "review", "reflection_score_threshold"),
    SCORE_THRESHOLD,
)

# 阶段 C：describe / CHANGELOG / 评论对话 / config.toml
AICR_DESCRIBE_ENABLED = toml_or_env_bool(
    "AICR_DESCRIBE_ENABLED",
    deep_get(_DEPLOY_CONFIG, "tools", "describe_enabled"),
    True,
)
AICR_DESCRIBE_UPDATE_MR = toml_or_env_bool(
    "AICR_DESCRIBE_UPDATE_MR",
    deep_get(_DEPLOY_CONFIG, "tools", "describe_update_mr"),
    False,
)
AICR_CHANGELOG_ENABLED = toml_or_env_bool(
    "AICR_CHANGELOG_ENABLED",
    deep_get(_DEPLOY_CONFIG, "tools", "changelog_enabled"),
    True,
)
AICR_ASK_ENABLED = toml_or_env_bool(
    "AICR_ASK_ENABLED",
    deep_get(_DEPLOY_CONFIG, "tools", "ask_enabled"),
    True,
)
AICR_ASK_TRIGGERS = toml_or_env_triggers(
    "AICR_ASK_TRIGGERS",
    deep_get(_DEPLOY_CONFIG, "ask", "triggers"),
    ["@aicr", "/ask"],
)
AICR_BOT_USERNAME = toml_or_env_str(
    "AICR_BOT_USERNAME",
    deep_get(_DEPLOY_CONFIG, "ask", "bot_username"),
    "aicr-bot",
)
AICR_WEBHOOK_NOTE_ENABLED = toml_or_env_bool(
    "AICR_WEBHOOK_NOTE_ENABLED",
    deep_get(_DEPLOY_CONFIG, "tools", "webhook_note_enabled"),
    True,
)
AICR_SUPPRESS_REVIEW_AFTER_DESCRIBE = toml_or_env_bool(
    "AICR_SUPPRESS_REVIEW_AFTER_DESCRIBE",
    deep_get(_DEPLOY_CONFIG, "tools", "suppress_review_after_describe"),
    True,
)
AICR_DESCRIBE_WEBHOOK_SUPPRESS_SECONDS = int(
    os.getenv(
        "AICR_DESCRIBE_WEBHOOK_SUPPRESS_SECONDS",
        str(deep_get(_DEPLOY_CONFIG, "tools", "describe_webhook_suppress_seconds") or 120),
    )
)

GITLAB_WEBHOOK_SECRET = os.getenv("GITLAB_WEBHOOK_SECRET", "")
GITLAB_WEBHOOK_ALLOW_INSECURE = os.getenv("GITLAB_WEBHOOK_ALLOW_INSECURE", "0") == "1"

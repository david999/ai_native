"""从 monorepo 环境文件加载配置。

加载顺序（``override=False``，先出现的变量优先）：

1. ``<repo>/evn/.env`` — 推荐的生产/本地统一配置
2. ``<repo>/.env``
3. ``aicr-reviewer/.env``

所有模块应 ``from app.config import ...`` 读取常量，避免散落 ``os.getenv``。
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# aicr-reviewer/app/config.py -> parents[2] = 仓库根目录
_MONOREPO_ROOT = Path(__file__).resolve().parents[2]


def _load_env_files() -> None:
    for path in (
        _MONOREPO_ROOT / "evn" / ".env",
        _MONOREPO_ROOT / ".env",
        Path(__file__).resolve().parents[1] / ".env",
    ):
        if path.is_file():
            load_dotenv(path, override=False)


_load_env_files()

GITLAB_URL = os.getenv("GITLAB_URL", "http://localhost:8000")
AICR_BOT_TOKEN = os.getenv("AICR_BOT_TOKEN", "")
SCORE_THRESHOLD = float(os.getenv("AICR_SCORE_THRESHOLD", "60"))
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

GITLAB_WEBHOOK_SECRET = os.getenv("GITLAB_WEBHOOK_SECRET", "")
GITLAB_WEBHOOK_ALLOW_INSECURE = os.getenv("GITLAB_WEBHOOK_ALLOW_INSECURE", "0") == "1"

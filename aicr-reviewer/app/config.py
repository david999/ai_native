import os
from pathlib import Path

from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ENV_FILE = _REPO_ROOT / ".env"
if _ENV_FILE.is_file():
    load_dotenv(_ENV_FILE)
else:
    load_dotenv()

# Local dev (native Python): localhost GitLab. Docker deploy: override to http://gitlab:8000
GITLAB_URL = os.getenv("GITLAB_URL", "http://localhost:8000")
AICR_BOT_TOKEN = os.getenv("AICR_BOT_TOKEN", "")
SCORE_THRESHOLD = float(os.getenv("AICR_SCORE_THRESHOLD", "60"))

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

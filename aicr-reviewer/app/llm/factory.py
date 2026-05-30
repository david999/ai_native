"""根据 LLM_PROVIDER 与环境变量创建 OpenAI 兼容客户端。"""

import logging

from app.config import LLM_PROVIDER, LLM_API_BASE, LLM_API_KEY, LLM_MODEL
from app.llm.base import LLMProvider
from app.llm.openai_compat import OpenAICompatibleProvider

logger = logging.getLogger("aicr")

_PROVIDER_MAP = {
    "ctyun_openai": {
        "api_base": "https://wishub-x6.ctyun.cn/v1",
    },
    "deepseek": {
        "api_base": "https://api.deepseek.com/v1",
    },
    "zhipu": {
        "api_base": "https://open.bigmodel.cn/api/paas/v4",
    },
    "openai": {
        "api_base": "https://api.openai.com/v1",
    },
}


def create_llm_provider(provider: str = LLM_PROVIDER) -> LLMProvider:
    preset = _PROVIDER_MAP.get(provider, {})
    api_base = LLM_API_BASE or preset.get("api_base", "")
    if not api_base:
        raise ValueError(f"LLM_API_BASE not set and no preset for provider '{provider}'")

    if not LLM_API_KEY:
        raise ValueError(f"LLM_API_KEY not set (required for provider '{provider}')")

    if not LLM_MODEL:
        raise ValueError(f"LLM_MODEL not set (required for provider '{provider}')")

    logger.info(f"Creating LLM provider: {provider}, base={api_base}, model={LLM_MODEL}")
    return OpenAICompatibleProvider(
        api_base=api_base,
        api_key=LLM_API_KEY,
        model=LLM_MODEL,
    )

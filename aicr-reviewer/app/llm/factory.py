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


def create_llm_provider(
    provider: str = LLM_PROVIDER,
    *,
    model: str | None = None,
    temperature: float | None = None,
) -> LLMProvider:
    preset = _PROVIDER_MAP.get(provider, {})
    api_base = LLM_API_BASE or preset.get("api_base", "")
    if not api_base:
        raise ValueError(f"LLM_API_BASE not set and no preset for provider '{provider}'")

    if not LLM_API_KEY:
        raise ValueError(f"LLM_API_KEY not set (required for provider '{provider}')")

    resolved_model = (model or "").strip() or LLM_MODEL
    if not resolved_model:
        raise ValueError(f"LLM_MODEL not set (required for provider '{provider}')")

    from app.config import LLM_TEMPERATURE

    resolved_temp = LLM_TEMPERATURE if temperature is None else temperature

    logger.info(
        f"Creating LLM provider: {provider}, base={api_base}, "
        f"model={resolved_model}, temperature={resolved_temp}"
    )
    return OpenAICompatibleProvider(
        api_base=api_base,
        api_key=LLM_API_KEY,
        model=resolved_model,
        temperature=resolved_temp,
    )


def create_llm_for_tool(
    tool: str,
    project_config: dict | None = None,
    provider: str = LLM_PROVIDER,
) -> LLMProvider:
    """阶段 C：按 config.toml ``[llm.<tool>]`` 或 ``LLM_MODEL_<TOOL>`` 创建客户端。"""
    from app.config_resolver import llm_settings_for_tool

    settings = llm_settings_for_tool(tool, project_config)
    return create_llm_provider(
        provider,
        model=settings.get("model"),
        temperature=settings.get("temperature"),
    )

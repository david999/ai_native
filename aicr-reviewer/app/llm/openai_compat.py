import logging
from typing import List, Dict, Optional

from openai import OpenAI

from app.config import (
    LLM_API_BASE, LLM_API_KEY, LLM_MODEL,
    LLM_TIMEOUT_SECONDS, LLM_MAX_TOKENS, LLM_TEMPERATURE,
)

logger = logging.getLogger("aicr")


class OpenAICompatibleProvider:
    def __init__(
        self,
        api_base: str = LLM_API_BASE,
        api_key: str = LLM_API_KEY,
        model: str = LLM_MODEL,
        timeout: int = LLM_TIMEOUT_SECONDS,
        max_tokens: int = LLM_MAX_TOKENS,
        temperature: float = LLM_TEMPERATURE,
    ):
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.client = OpenAI(
            base_url=api_base,
            api_key=api_key,
            timeout=timeout,
            default_headers={"User-Agent": "aicr-reviewer/1.0"},
        )

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        json_mode: bool = True,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        logger.info(f"LLM request: model={self.model}, messages={len(messages)}, json_mode={json_mode}")
        try:
            resp = self.client.chat.completions.create(**kwargs)
            content = resp.choices[0].message.content or ""
            usage = resp.usage
            if usage:
                logger.info(
                    f"LLM usage: prompt_tokens={usage.prompt_tokens}, "
                    f"completion_tokens={usage.completion_tokens}, "
                    f"total_tokens={usage.total_tokens}"
                )
            return content
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

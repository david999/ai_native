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
        base_kwargs: dict = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
        }

        logger.info(
            f"LLM request: model={self.model}, messages={len(messages)}, "
            f"json_mode={json_mode}"
        )

        if json_mode:
            try:
                return self._complete({**base_kwargs, "response_format": {"type": "json_object"}})
            except Exception as e:
                if self._json_mode_unsupported(e):
                    logger.warning("json_mode unsupported, retrying without response_format")
                    return self._complete(base_kwargs)
                raise

        return self._complete(base_kwargs)

    def _complete(self, kwargs: dict) -> str:
        resp = self.client.chat.completions.create(**kwargs)
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        if usage:
            logger.info(
                f"LLM usage: prompt={usage.prompt_tokens}, "
                f"completion={usage.completion_tokens}, total={usage.total_tokens}"
            )
        return content

    @staticmethod
    def _json_mode_unsupported(exc: Exception) -> bool:
        msg = str(exc).lower()
        return "response_format" in msg or "json_object" in msg or "unsupported" in msg

"""OpenAI Chat Completions 实现；不支持 json_object 时自动降级为普通 completion。

若已安装 opentelemetry-sdk，自动为每次 LLM 调用生成 span，记录 token 消耗、延迟等指标。
"""

import logging
import time
from typing import List, Dict, Optional

from openai import OpenAI

from app.config import (
    LLM_API_BASE, LLM_API_KEY, LLM_MODEL,
    LLM_TIMEOUT_SECONDS, LLM_MAX_TOKENS, LLM_TEMPERATURE,
)

logger = logging.getLogger("aicr")


def _get_tracer():
    """懒加载 OpenTelemetry tracer；未安装时返回 None，不影响主流程。"""
    try:
        from opentelemetry import trace
        return trace.get_tracer("aicr.llm")
    except ImportError:
        return None


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
        tracer = _get_tracer()
        start = time.monotonic()

        if tracer is None:
            resp = self.client.chat.completions.create(**kwargs)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            return self._log_usage(resp, elapsed_ms)

        with tracer.start_as_current_span(
            "llm.chat",
            attributes={
                "llm.provider": "openai_compat",
                "llm.model": self.model,
                "llm.max_tokens": kwargs.get("max_tokens", self.max_tokens),
            },
        ) as span:
            resp = self.client.chat.completions.create(**kwargs)
            elapsed_ms = int((time.monotonic() - start) * 1000)
            content = resp.choices[0].message.content or ""
            usage = resp.usage
            if usage:
                logger.info(
                    f"LLM usage: prompt={usage.prompt_tokens}, "
                    f"completion={usage.completion_tokens}, total={usage.total_tokens}, "
                    f"latency={elapsed_ms}ms"
                )
                try:
                    span.set_attribute("llm.prompt_tokens", usage.prompt_tokens)
                    span.set_attribute("llm.completion_tokens", usage.completion_tokens)
                    span.set_attribute("llm.total_tokens", usage.total_tokens)
                    span.set_attribute("llm.latency_ms", elapsed_ms)
                except Exception:
                    pass
            else:
                logger.info(f"LLM call completed: latency={elapsed_ms}ms")
            return content

    def _log_usage(self, resp, elapsed_ms: int) -> str:
        """无 tracer 路径的日志输出并返回内容。"""
        content = resp.choices[0].message.content or ""
        usage = resp.usage
        if usage:
            logger.info(
                f"LLM usage: prompt={usage.prompt_tokens}, "
                f"completion={usage.completion_tokens}, total={usage.total_tokens}, "
                f"latency={elapsed_ms}ms"
            )
        else:
            logger.info(f"LLM call completed: latency={elapsed_ms}ms")
        return content

    @staticmethod
    def _json_mode_unsupported(exc: Exception) -> bool:
        msg = str(exc).lower()
        return "response_format" in msg or "json_object" in msg or "unsupported" in msg

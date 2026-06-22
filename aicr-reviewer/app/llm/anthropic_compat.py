"""Anthropic Messages API 实现；兼容 LLMProvider 协议。

通过 anthropic 官方 SDK 调用 Claude 系列模型。
JSON 模式：在 system prompt 末尾追加 JSON 指令，并做正则兜底（Anthropic 不支持 response_format）。
"""

import logging
import re
from typing import List, Dict, Optional

from app.config import (
    LLM_API_KEY,
    LLM_MODEL,
    LLM_TIMEOUT_SECONDS,
    LLM_MAX_TOKENS,
    LLM_TEMPERATURE,
)

logger = logging.getLogger("aicr")

_JSON_INSTRUCTION = (
    "\n\nIMPORTANT: You MUST respond with a valid JSON object only. "
    "Do not include any text outside the JSON."
)


class AnthropicProvider:
    """Anthropic Messages API 兼容 LLMProvider。

    要求安装：pip install anthropic>=0.25.0
    """

    def __init__(
        self,
        api_key: str = LLM_API_KEY,
        model: str = LLM_MODEL,
        timeout: int = LLM_TIMEOUT_SECONDS,
        max_tokens: int = LLM_MAX_TOKENS,
        temperature: float = LLM_TEMPERATURE,
        api_base: str = "",
    ):
        try:
            import anthropic as _anthropic  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                "anthropic package is required for AnthropicProvider. "
                "Install it with: pip install anthropic>=0.25.0"
            ) from exc

        import anthropic

        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature

        client_kwargs: dict = {"api_key": api_key, "timeout": timeout}
        if api_base:
            client_kwargs["base_url"] = api_base

        self.client = anthropic.Anthropic(**client_kwargs)

    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        json_mode: bool = True,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        # Anthropic 要求 system 与 messages 分离
        system_content = ""
        user_messages: List[Dict[str, str]] = []
        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")
            if role == "system":
                system_content = content
            else:
                user_messages.append({"role": role, "content": content})

        if json_mode and system_content:
            system_content = system_content + _JSON_INSTRUCTION
        elif json_mode:
            system_content = _JSON_INSTRUCTION.strip()

        resolved_max_tokens = max_tokens or self.max_tokens
        resolved_temp = temperature if temperature is not None else self.temperature

        logger.info(
            f"Anthropic request: model={self.model}, messages={len(user_messages)}, "
            f"json_mode={json_mode}"
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=resolved_max_tokens,
            temperature=resolved_temp,
            system=system_content,
            messages=user_messages,
        )

        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        usage = response.usage
        if usage:
            logger.info(
                f"Anthropic usage: input={usage.input_tokens}, "
                f"output={usage.output_tokens}"
            )

        if json_mode:
            # 兜底：提取 JSON 块（Anthropic 有时在 JSON 前后输出少量文字）
            content = self._extract_json_fallback(content)

        return content

    @staticmethod
    def _extract_json_fallback(text: str) -> str:
        """若响应不是纯 JSON，尝试提取第一个完整 JSON 对象。"""
        stripped = text.strip()
        if stripped.startswith("{"):
            return stripped
        # 尝试提取 ```json ... ``` 块
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped)
        if m:
            return m.group(1).strip()
        # 尝试提取第一个 { ... }
        m = re.search(r"\{[\s\S]*\}", stripped)
        if m:
            return m.group(0)
        return text

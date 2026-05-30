"""LLM 提供商抽象：便于测试注入 Mock 与切换实现。"""

from typing import Protocol, List, Dict, Any, Optional


class LLMProvider(Protocol):
    """OpenAI Chat Completions 兼容接口；json_mode 时期望返回可解析的 JSON 字符串。"""
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        json_mode: bool = True,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        ...

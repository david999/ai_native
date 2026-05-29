from typing import Protocol, List, Dict, Any, Optional


class LLMProvider(Protocol):
    def chat(
        self,
        messages: List[Dict[str, str]],
        *,
        json_mode: bool = True,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        ...

"""阶段 C 工具 JSON 解析（与 review parser 分离的轻量 schema）。"""

from __future__ import annotations

import json
import re
from typing import Any, Dict

from app.review.parser import ParseError


class ToolResponseParser:
    @staticmethod
    def _extract_json(raw: str) -> dict:
        text = raw.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise ParseError("No JSON object in LLM response")
        return json.loads(text[start : end + 1])

    def parse_describe(self, raw: str) -> Dict[str, Any]:
        data = self._extract_json(raw)
        title = str(data.get("title", "")).strip()
        description = str(data.get("description", "")).strip()
        if not description:
            raise ParseError("describe response missing description")
        return {"title": title, "description": description}

    def parse_changelog(self, raw: str) -> Dict[str, Any]:
        data = self._extract_json(raw)
        changelog = str(data.get("changelog", "")).strip()
        summary = str(data.get("summary", "")).strip()
        if not changelog:
            raise ParseError("changelog response missing changelog")
        return {"changelog": changelog, "summary": summary}

    def parse_ask(self, raw: str) -> Dict[str, Any]:
        data = self._extract_json(raw)
        answer = str(data.get("answer", "")).strip()
        if not answer:
            raise ParseError("ask response missing answer")
        return {"answer": answer}

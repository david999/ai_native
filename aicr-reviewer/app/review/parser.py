import json
import logging
import re
from typing import Dict, Any, List, Optional

logger = logging.getLogger("aicr")


class ParseError(Exception):
    """LLM response could not be parsed into review JSON."""


class StructuredResponseParser:
    def parse(self, raw: str) -> Dict[str, Any]:
        text = raw.strip()

        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text)
            text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Direct JSON parse failed, attempting extraction")
            data = self._extract_json(text)
            if data is None:
                raise ParseError(f"Could not parse LLM response (len={len(raw)})")

        return self._normalize(data)

    @staticmethod
    def _extract_json(text: str) -> Optional[Any]:
        for pattern in (
            r'\{[\s\S]*"score"[\s\S]*"issues"[\s\S]*\}',
            r'\{[\s\S]*\}',
        ):
            for match in re.findall(pattern, text):
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
        return None

    @staticmethod
    def _safe_line(value: Any) -> int:
        try:
            return max(0, int(value or 0))
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize(data: Dict) -> Dict[str, Any]:
        score = data.get("score", 0)
        try:
            score = float(score)
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(100.0, score))

        summary = str(data.get("summary", ""))

        issues: List[Dict] = []
        for item in data.get("issues", []):
            if not isinstance(item, dict):
                continue
            issues.append({
                "file": str(item.get("file", "")),
                "line": StructuredResponseParser._safe_line(item.get("line")),
                "severity": str(item.get("severity", "info")),
                "category": str(item.get("category", "other")),
                "message": str(item.get("message", "")),
                "suggestion": str(item.get("suggestion", "")),
            })

        return {"score": score, "summary": summary, "issues": issues}

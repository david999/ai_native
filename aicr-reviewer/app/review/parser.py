import json
import logging
import re
from typing import Dict, Any, List

logger = logging.getLogger("aicr")


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
            logger.warning("Direct JSON parse failed, attempting extraction from text")
            data = self._extract_json(text)
            if data is None:
                logger.error("Could not parse LLM response as JSON")
                return self._fallback(raw)

        return self._normalize(data)

    @staticmethod
    def _extract_json(text: str) -> Any:
        patterns = [
            r'\{[\s\S]*"score"[\s\S]*"issues"[\s\S]*\}',
            r'\{[\s\S]*\}',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    return json.loads(match)
                except json.JSONDecodeError:
                    continue
        return None

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
                "line": int(item.get("line", 0) or 0),
                "severity": str(item.get("severity", "info")),
                "category": str(item.get("category", "other")),
                "message": str(item.get("message", "")),
                "suggestion": str(item.get("suggestion", "")),
            })

        return {"score": score, "summary": summary, "issues": issues}

    @staticmethod
    def _fallback(raw: str) -> Dict[str, Any]:
        return {
            "score": 50.0,
            "summary": f"LLM response could not be parsed. Raw length: {len(raw)}",
            "issues": [],
        }

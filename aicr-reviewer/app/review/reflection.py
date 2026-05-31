"""Self-reflection：对初评结果做二次校验，降低幻觉与误报。"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from app.config import AICR_REFLECTION_SCORE_THRESHOLD, AICR_SELF_REFLECTION
from app.llm.base import LLMProvider
from app.review.parser import ParseError, StructuredResponseParser
from app.review.prompt_renderer import PromptRenderer

logger = logging.getLogger("aicr")

_REFLECTION_SEVERITIES = frozenset({"critical", "major"})


def should_reflect(score: float, issues: List[dict]) -> bool:
    if not AICR_SELF_REFLECTION:
        return False
    threshold = AICR_REFLECTION_SCORE_THRESHOLD
    if score < threshold:
        return True
    return any(
        str(i.get("severity", "")).lower() in _REFLECTION_SEVERITIES for i in issues
    )


def run_reflection(
    llm: LLMProvider,
    renderer: PromptRenderer,
    parser: StructuredResponseParser,
    *,
    language_hint: str,
    context_md: str,
    mr_title: str,
    mr_description: str,
    diff_text: str,
    initial: Dict[str, Any],
) -> Dict[str, Any]:
    """对初评 JSON 做 reflection pass；失败时返回 initial。"""
    system_prompt = renderer.render_reflection_system(
        context_md=context_md,
        language_hint=language_hint,
    )
    user_prompt = renderer.render_reflection_user(
        mr_title=mr_title,
        mr_description=mr_description,
        diff_text=diff_text,
        initial_review_json=json.dumps(initial, ensure_ascii=False, indent=2),
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw = llm.chat(messages, json_mode=True)
        result = parser.parse(raw)
        logger.info(
            f"Reflection pass: score {initial.get('score')} -> {result.get('score')}, "
            f"issues {len(initial.get('issues', []))} -> {len(result.get('issues', []))}"
        )
        return result
    except (ParseError, Exception) as e:
        logger.warning(f"Reflection pass failed, keeping initial review: {e}")
        return initial

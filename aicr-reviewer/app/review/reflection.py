"""Self-reflection：对初评结果做二次校验，降低幻觉与误报。

触发条件（可独立配置）：
- 分数 < AICR_REFLECTION_SCORE_THRESHOLD：由分数触发的针对性反思
- 存在 critical 问题 且 AICR_REFLECTION_ON_CRITICAL=1：对高危问题做二次校验（可独立关闭）
- 过滤异常：过滤后无 issue 且有 drop 时触发疑似幻觉检查
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

from app.config import (
    AICR_REFLECTION_SCORE_THRESHOLD,
    AICR_SELF_REFLECTION,
    AICR_REFLECTION_ON_CRITICAL,
    AICR_REFLECTION_TEMPERATURE,
)
from app.llm.base import LLMProvider
from app.review.parser import ParseError, StructuredResponseParser
from app.review.prompt_renderer import PromptRenderer

logger = logging.getLogger("aicr")


def should_reflect(
    score: float,
    issues: List[dict],
    *,
    filtered_dropped: int = 0,
    pre_filter_count: int = 0,
) -> bool:
    if not AICR_SELF_REFLECTION:
        return False
    # 条件 1：分数低于阈值（防止高分但存在 critical 时不必要触发）
    if score < AICR_REFLECTION_SCORE_THRESHOLD:
        return True
    # 条件 2：存在 critical 且该功能未单独关闭
    if AICR_REFLECTION_ON_CRITICAL and any(
        str(i.get("severity", "")).lower() == "critical" for i in issues
    ):
        return True
    # 条件 3：过滤异常（过滤后无 issue 且有 drop）
    if filtered_dropped > 0 and pre_filter_count > 0 and not issues:
        return True
    return False


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
    """对初评 JSON 做 reflection pass；失败时返回 initial。

    使用独立可配置的 temperature（AICR_REFLECTION_TEMPERATURE），
    默认比初评更低（降低确认偏误风险）。
    """
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
        raw = llm.chat(
            messages,
            json_mode=True,
            temperature=AICR_REFLECTION_TEMPERATURE,
        )
        result = parser.parse(raw)
        logger.info(
            f"Reflection pass: score {initial.get('score')} -> {result.get('score')}, "
            f"issues {len(initial.get('issues', []))} -> {len(result.get('issues', []))}"
        )
        return result
    except (ParseError, Exception) as e:
        logger.warning(f"Reflection pass failed, keeping initial review: {e}")
        return initial

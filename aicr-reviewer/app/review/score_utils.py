"""根据剩余 issue 严重程度推导分数，并与 chunk 聚合分 reconcile。"""

from __future__ import annotations

from typing import List

_SEVERITY_PENALTY = {
    "critical": 45.0,
    "major": 28.0,
    "minor": 12.0,
    "info": 5.0,
}


def score_from_issues(issues: List[dict]) -> float:
    """无 issue 视为 100；否则按最严重项累计扣分。"""
    if not issues:
        return 100.0

    score = 100.0
    for issue in issues:
        sev = str(issue.get("severity", "info")).lower()
        score -= _SEVERITY_PENALTY.get(sev, 10.0)
    return max(0.0, min(100.0, score))


def reconcile_score(
    chunk_min_score: float,
    issues: List[dict],
    *,
    filtered_dropped: int,
) -> float:
    """过滤掉幻觉 issue 后，用剩余 issue 重算分并与 chunk 最低分 reconcile。"""
    derived = score_from_issues(issues)

    if filtered_dropped <= 0:
        if not issues:
            return chunk_min_score
        return min(chunk_min_score, derived)

    if not issues:
        return max(chunk_min_score, derived)

    return min(chunk_min_score, derived)

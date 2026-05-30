"""评审流水线异常层次。

- NoReviewableChangesError：无支持扩展名的变更 → API 返回 score=100
- LLMReviewError：LLM 或解析失败 → API 503，CI fail-open
"""


class ReviewError(Exception):
    """Base class for review failures that should not pass as score=100."""


class LLMReviewError(ReviewError):
    """LLM provider call or response failed."""


class NoReviewableChangesError(ReviewError):
    """MR has no supported file changes to review."""

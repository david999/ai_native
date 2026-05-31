"""评审流水线异常层次。

- NoReviewableChangesError：无支持扩展名的变更 → API 返回 score=100
- LLMReviewError（全部分块失败）/ ReviewError / 其它运行时异常 → API 200 + score=100（fail-open）
- 部分分块失败 → review_completed=false（CI 不放行低分拦截）
- 鉴权失败 → HTTP 401/503（不 fail-open）
"""


class ReviewError(Exception):
    """Base class for review failures that should not pass as score=100."""


class LLMReviewError(ReviewError):
    """LLM provider call or response failed."""


class NoReviewableChangesError(ReviewError):
    """MR has no supported file changes to review."""

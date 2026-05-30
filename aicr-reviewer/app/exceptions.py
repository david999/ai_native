"""Review pipeline exceptions."""


class ReviewError(Exception):
    """Base class for review failures that should not pass as score=100."""


class LLMReviewError(ReviewError):
    """LLM provider call or response failed."""


class NoReviewableChangesError(ReviewError):
    """MR has no supported file changes to review."""

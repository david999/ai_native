"""限制并发评审数量，避免 LLM/GitLab 资源被瞬时打满。"""

import threading

from app.config import REVIEW_MAX_CONCURRENT

_semaphore = threading.Semaphore(REVIEW_MAX_CONCURRENT)


class ReviewCapacityError(Exception):
    """当前并发评审已达上限。"""


def acquire_review_slot(blocking: bool = True, timeout: float | None = 30.0) -> None:
    """获取评审槽位；无法获取时抛出 ReviewCapacityError。"""
    acquired = _semaphore.acquire(blocking=blocking, timeout=timeout if blocking else 0)
    if not acquired:
        raise ReviewCapacityError(
            f"Too many concurrent reviews (max={REVIEW_MAX_CONCURRENT})"
        )


def release_review_slot() -> None:
    _semaphore.release()

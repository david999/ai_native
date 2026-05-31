"""限制并发评审数量；同一 MR 互斥，避免重复 LLM/GitLab 调用。"""

from __future__ import annotations

import threading
from typing import Dict, Tuple

from app.config import REVIEW_MAX_CONCURRENT

_semaphore = threading.Semaphore(REVIEW_MAX_CONCURRENT)

_mr_locks: Dict[Tuple[int, int], threading.Lock] = {}
_mr_locks_guard = threading.Lock()


class ReviewCapacityError(Exception):
    """当前并发评审已达上限。"""


class MRReviewBusyError(Exception):
    """同一 MR 已有评审在进行中。"""


def acquire_review_slot(blocking: bool = True, timeout: float | None = 30.0) -> None:
    """获取全局评审槽位；无法获取时抛出 ReviewCapacityError。"""
    acquired = _semaphore.acquire(blocking=blocking, timeout=timeout if blocking else 0)
    if not acquired:
        raise ReviewCapacityError(
            f"Too many concurrent reviews (max={REVIEW_MAX_CONCURRENT})"
        )


def release_review_slot() -> None:
    _semaphore.release()


def _get_mr_lock(project_id: int, mr_iid: int) -> threading.Lock:
    key = (project_id, mr_iid)
    with _mr_locks_guard:
        if key not in _mr_locks:
            _mr_locks[key] = threading.Lock()
        return _mr_locks[key]


def acquire_mr_review(
    project_id: int,
    mr_iid: int,
    *,
    blocking: bool = True,
    timeout: float | None = 30.0,
) -> None:
    """获取 per-MR 锁；无法获取时抛出 MRReviewBusyError。"""
    lock = _get_mr_lock(project_id, mr_iid)
    acquired = lock.acquire(blocking=blocking, timeout=timeout if blocking else 0)
    if not acquired:
        raise MRReviewBusyError(
            f"Review already in progress for project={project_id} MR !{mr_iid}"
        )


def release_mr_review(project_id: int, mr_iid: int) -> None:
    lock = _get_mr_lock(project_id, mr_iid)
    if lock.locked():
        lock.release()


def reset_mr_locks_for_tests() -> None:
    """测试用：清空 MR 锁表（勿在生产调用）。"""
    with _mr_locks_guard:
        _mr_locks.clear()

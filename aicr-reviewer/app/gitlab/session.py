"""GitLab MR 会话：缓存 project/mr 对象，并对 API 调用做超时与有限重试。"""

import logging
import time
from typing import Any, Callable, TypeVar

import gitlab
from gitlab.exceptions import GitlabError

from app.config import GITLAB_TIMEOUT_SECONDS, GITLAB_API_RETRIES
from app.gitlab.client import get_gitlab_client

logger = logging.getLogger("aicr")

T = TypeVar("T")


def gitlab_call(fn: Callable[[], T], *, retries: int | None = None) -> T:
    """对 GitLab SDK 调用做指数退避重试（仅重试 GitlabError）。"""
    max_attempts = retries if retries is not None else GITLAB_API_RETRIES
    last_exc: Exception | None = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except GitlabError as e:
            last_exc = e
            if attempt >= max_attempts - 1:
                break
            delay = 0.5 * (2**attempt)
            logger.warning(f"GitLab API error (attempt {attempt + 1}/{max_attempts}): {e}")
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc


class GitLabMRSession:
    """同一评审批次内复用 project / merge request 对象，减少重复 API 请求。"""

    def __init__(self, project_id: int, mr_iid: int):
        self.project_id = project_id
        self.mr_iid = mr_iid
        self._project: Any = None
        self._mr: Any = None

    @property
    def project(self) -> Any:
        if self._project is None:
            gl = get_gitlab_client()
            self._project = gitlab_call(lambda: gl.projects.get(self.project_id))
        return self._project

    @property
    def mr(self) -> Any:
        if self._mr is None:
            self._mr = gitlab_call(
                lambda: self.project.mergerequests.get(self.mr_iid)
            )
        return self._mr

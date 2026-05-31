"""GitLab Python SDK 客户端单例，全进程复用同一连接配置。"""

import gitlab
from app.config import GITLAB_URL, AICR_BOT_TOKEN, GITLAB_TIMEOUT_SECONDS

_gl_instance = None


def get_gitlab_client() -> gitlab.Gitlab:
    global _gl_instance
    if _gl_instance is None:
        _gl_instance = gitlab.Gitlab(
            GITLAB_URL,
            private_token=AICR_BOT_TOKEN,
            timeout=GITLAB_TIMEOUT_SECONDS,
        )
    return _gl_instance

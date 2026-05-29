import gitlab
from app.config import GITLAB_URL, AICR_BOT_TOKEN

_gl_instance = None


def get_gitlab_client() -> gitlab.Gitlab:
    global _gl_instance
    if _gl_instance is None:
        _gl_instance = gitlab.Gitlab(GITLAB_URL, private_token=AICR_BOT_TOKEN)
    return _gl_instance

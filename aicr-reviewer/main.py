"""AICR Reviewer 应用入口。

使用 uvicorn 启动，例如::

    uvicorn main:app --host 0.0.0.0 --port 8001

环境变量从仓库 ``evn/.env`` 加载，详见 ``docs/SECRETS.md``。
"""

import logging
from fastapi import FastAPI

from app.api.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

app = FastAPI(
    title="AICR Reviewer",
    version="2.0.0",
    description="LLM-powered code review for GitLab merge requests",
)
app.include_router(router)


@app.on_event("startup")
def _log_review_api_auth_mode() -> None:
    from app.config import REVIEW_API_ALLOW_INSECURE, REVIEW_API_SECRET

    logger = logging.getLogger("aicr")
    if REVIEW_API_SECRET:
        logger.info("Review API auth: REVIEW_API_SECRET configured")
    elif REVIEW_API_ALLOW_INSECURE:
        logger.warning(
            "Review API auth: REVIEW_API_ALLOW_INSECURE=1 (local/dev only; do not use in production)"
        )
    else:
        logger.warning(
            "Review API auth: no secret; POST /review returns 503 until "
            "REVIEW_API_SECRET or REVIEW_API_ALLOW_INSECURE=1"
        )

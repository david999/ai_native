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

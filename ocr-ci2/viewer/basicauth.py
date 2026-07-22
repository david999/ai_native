"""可选的 Dashboard Basic Auth 中间件。

仅在设置环境变量 ``OCR_DASHBOARD_USER`` 与 ``OCR_DASHBOARD_PASSWORD`` 后启用，
保护 Dashboard HTML 与 JSON API（不影响 ``/health``、``/docs`` 等被显式放行的路径）。

参考：AI-Codereview-Gitlab 的简单账号密码登录思路，但用 HTTP Basic 减少状态管理。
"""

from __future__ import annotations

import base64
import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# 不需要鉴权的路径前缀（健康检查、OpenAPI 文档等）
_PUBLIC_PREFIXES = ("/health", "/docs", "/openapi.json", "/redoc")


class BasicAuthMiddleware(BaseHTTPMiddleware):
    """对 Dashboard 路由做 Basic Auth 校验。

    - 放行 ``_PUBLIC_PREFIXES`` 开头的路径
    - 其余路径要求 ``Authorization: Basic <base64(user:pass)>`` 且匹配配置的账号密码
    - 校验失败返回 401 + ``WWW-Authenticate: Basic`` 触发浏览器登录框
    """

    def __init__(self, app, *, username: str, password: str, realm: str = "OCR Gateway Dashboard") -> None:
        super().__init__(app)
        self._username = username
        self._password = password
        self._realm = realm

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if any(path == p or path.startswith(p + "/") for p in _PUBLIC_PREFIXES):
            return await call_next(request)

        header = request.headers.get("authorization", "")
        if not header.lower().startswith("basic "):
            return self._unauthorized()

        try:
            decoded = base64.b64decode(header[6:].strip()).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return self._unauthorized()

        if ":" not in decoded:
            return self._unauthorized()

        user, _, password = decoded.partition(":")
        # 两个 compare_digest 均在 if 之前执行，避免「用户名错/密码错」的时序区分
        user_ok = hmac.compare_digest(user, self._username)
        pass_ok = hmac.compare_digest(password, self._password)
        if not (user_ok and pass_ok):
            return self._unauthorized()

        return await call_next(request)

    def _unauthorized(self) -> Response:
        return Response(
            status_code=401,
            headers={"WWW-Authenticate": f'Basic realm="{self._realm}", charset="UTF-8"'},
        )

"""Host header guard for local Severity Dashboard (mirrors OCR official viewer)."""

from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response

_LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1", "0:0:0:0:0:0:0:1"})


def _host_only(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("[") and "]" in value:
        end = value.index("]")
        return value[1:end].lower()
    if ":" in value and value.count(":") == 1:
        return value.rsplit(":", 1)[0].lower()
    return value.lower()


def _is_loopback(host: str) -> bool:
    if host in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _allowed_hosts(bind_host: str) -> frozenset[str]:
    allowed = set(_LOOPBACK_NAMES)
    bind_host = _host_only(bind_host)
    if bind_host and bind_host not in ("0.0.0.0", "::", "*"):
        allowed.add(bind_host)
    extra = os.environ.get("SEVERITY_VIEWER_ALLOWED_HOSTS", "")
    for part in extra.split(","):
        h = _host_only(part.strip())
        if h:
            allowed.add(h)
    return frozenset(allowed)


def host_allowed(request: Request, bind_host: str) -> bool:
    host = _host_only(request.headers.get("host", ""))
    if not host:
        return False
    if _is_loopback(host):
        return True
    return host in _allowed_hosts(bind_host)


class HostGuardMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, bind_host: str = "127.0.0.1") -> None:
        super().__init__(app)
        self.bind_host = bind_host

    async def dispatch(self, request: Request, call_next) -> Response:
        if not host_allowed(request, self.bind_host):
            return PlainTextResponse("forbidden host", status_code=403)
        return await call_next(request)

"""Host guard for Severity Dashboard."""

from __future__ import annotations

from starlette.requests import Request

from viewer.hostguard import HostGuardMiddleware, host_allowed


def _request(host: str) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": [(b"host", host.encode())],
    }
    return Request(scope)


def test_host_allowed_loopback():
    assert host_allowed(_request("localhost:5484"), "127.0.0.1")
    assert host_allowed(_request("127.0.0.1:5484"), "127.0.0.1")


def test_host_allowed_rejects_unknown(monkeypatch):
    monkeypatch.delenv("SEVERITY_VIEWER_ALLOWED_HOSTS", raising=False)
    assert not host_allowed(_request("evil.example.com"), "127.0.0.1")


def test_host_guard_middleware_class():
    assert HostGuardMiddleware is not None

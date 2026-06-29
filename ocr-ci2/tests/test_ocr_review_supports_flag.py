"""ocr_review_supports_flag 探测逻辑测试。"""

from __future__ import annotations

import importlib
import subprocess
from types import SimpleNamespace


def _reload_config():
    import gateway.config as cfg

    cfg.ocr_review_supports_flag.cache_clear()
    return importlib.reload(cfg)


def test_ocr_review_supports_exclude_via_semver(monkeypatch):
    cfg = _reload_config()

    def fake_run(cmd, **kwargs):
        if cmd[-1] == "version":
            return SimpleNamespace(stdout="open-code-review v1.6.5\n", stderr="", returncode=0)
        return SimpleNamespace(stdout="--max-tools int\n", stderr="", returncode=0)

    monkeypatch.setattr(cfg, "resolve_executable", lambda name: "/usr/bin/ocr")
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert cfg.ocr_review_supports_flag("--exclude") is True
    assert cfg.ocr_review_supports_flag("--max-tools") is True


def test_ocr_review_supports_exclude_via_probe_when_missing_from_help(monkeypatch):
    cfg = _reload_config()

    def fake_run(cmd, **kwargs):
        if cmd[-1] == "version":
            return SimpleNamespace(stdout="", stderr="", returncode=0)
        if "--exclude" in cmd and "__ocr_probe__" in cmd:
            return SimpleNamespace(
                stdout="",
                stderr="Error: /tmp is not a git repository",
                returncode=1,
            )
        return SimpleNamespace(stdout="--max-tools int\n", stderr="", returncode=0)

    monkeypatch.setattr(cfg, "resolve_executable", lambda name: "/usr/bin/ocr")
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert cfg.ocr_review_supports_flag("--exclude") is True
    assert cfg.ocr_review_supports_flag("--unknown-flag") is False


def test_ocr_review_supports_exclude_false_when_flag_undefined(monkeypatch):
    cfg = _reload_config()

    def fake_run(cmd, **kwargs):
        if cmd[-1] == "version":
            return SimpleNamespace(stdout="open-code-review v1.3.19\n", stderr="", returncode=0)
        if "--exclude" in cmd:
            return SimpleNamespace(
                stdout="",
                stderr="flag provided but not defined: -exclude",
                returncode=1,
            )
        return SimpleNamespace(stdout="", stderr="", returncode=0)

    monkeypatch.setattr(cfg, "resolve_executable", lambda name: "/usr/bin/ocr")
    monkeypatch.setattr(subprocess, "run", fake_run)

    assert cfg.ocr_review_supports_flag("--exclude") is False

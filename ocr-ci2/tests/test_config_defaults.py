"""gateway.config 默认解析测试。

覆盖：POST_SCRIPT、GitLab URL 默认值、deploy/local/gateway.env.example 存在。
不测：install 脚本、npm/ocr CLI。
"""
from __future__ import annotations

import importlib
import os
from pathlib import Path


def _reload_config():
    import gateway.config as cfg

    return importlib.reload(cfg)


def test_default_post_script_points_to_repo():
    os.environ.pop("OCR_POST_SCRIPT", None)
    cfg = _reload_config()
    repo_root = Path(__file__).resolve().parents[1]
    expected = repo_root / "scripts" / "post_ocr_to_gitlab.py"
    assert cfg.POST_SCRIPT == str(expected.resolve())


def test_default_gitlab_url_localhost_when_native_env_unset():
    os.environ.pop("OCR_GATEWAY_GITLAB_URL", None)
    cfg = _reload_config()
    assert cfg.GITLAB_INTERNAL_URL == "http://localhost:8000"


def test_explicit_gitlab_url_overrides_default():
    os.environ["OCR_GATEWAY_GITLAB_URL"] = "http://gitlab:8000"
    cfg = _reload_config()
    assert cfg.GITLAB_INTERNAL_URL == "http://gitlab:8000"
    os.environ.pop("OCR_GATEWAY_GITLAB_URL", None)
    _reload_config()


def test_gateway_native_env_example_exists():
    repo_root = Path(__file__).resolve().parents[1]
    example = repo_root / "deploy" / "local" / "gateway.env.example"
    assert example.is_file()
    text = example.read_text(encoding="utf-8")
    assert "OCR_GATEWAY_SECRET" in text
    assert "localhost:8000" in text
    assert "OCR_REVIEW_EXCLUDE" in text

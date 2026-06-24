from __future__ import annotations

from ocr_ci_config import gitlab_api_token_from_config, resolve_gitlab_api_token


def test_gitlab_api_token_from_nested_dict():
    data = {"gitlab": {"api_token": "glpat-test"}}
    assert gitlab_api_token_from_config(data) == "glpat-test"


def test_gitlab_api_token_legacy_top_level():
    assert gitlab_api_token_from_config({"gitlab_api_token": "legacy"}) == "legacy"


def test_resolve_gitlab_api_token_from_env_path(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text('{"gitlab": {"api_token": "from-env-path"}}', encoding="utf-8")
    monkeypatch.setenv("OCR_CONFIG_PATH", str(cfg))
    assert resolve_gitlab_api_token() == "from-env-path"

from __future__ import annotations

import pytest

from bake_ocr_config import (
    build_config,
    deep_merge,
    llm_url_from_base,
    validate_baked_config,
)


def test_llm_url_from_base_appends_chat_completions():
    assert llm_url_from_base("https://api.example/v1") == (
        "https://api.example/v1/chat/completions"
    )


def test_llm_url_from_base_keeps_full_url():
    url = "https://api.example/v1/chat/completions"
    assert llm_url_from_base(url) == url


def test_deep_merge_nested_llm():
    base = {"llm": {"url": "a", "model": "m1"}, "gitlab": {"api_token": "x"}}
    overlay = {"llm": {"auth_token": "sk-test"}}
    merged = deep_merge(base, overlay)
    assert merged["llm"]["url"] == "a"
    assert merged["llm"]["auth_token"] == "sk-test"
    assert merged["gitlab"]["api_token"] == "x"


def test_validate_baked_config_ok():
    cfg = {
        "llm": {
            "url": "https://api.example/v1/chat/completions",
            "auth_token": "sk",
            "model": "m",
        },
        "gitlab": {"api_token": "glpat-x"},
    }
    assert validate_baked_config(cfg) == []


def test_validate_baked_config_missing_fields():
    missing = validate_baked_config({"llm": {"url": "https://x/v1"}})
    assert "llm.auth_token" in missing
    assert "llm.model" in missing
    assert "gitlab.api_token" in missing


def test_validate_baked_config_rejects_bad_url():
    cfg = {
        "llm": {
            "url": "https://api.example/v1",
            "auth_token": "sk",
            "model": "m",
        },
        "gitlab": {"api_token": "glpat-x"},
    }
    assert any("chat/completions" in m for m in validate_baked_config(cfg))


def test_build_config_merges_env_file(tmp_path):
    env = tmp_path / ".env"
    env.write_text(
        "LLM_API_BASE=https://env.example/v1\nLLM_API_KEY=from-env\nLLM_MODEL=env-model\n",
        encoding="utf-8",
    )
    cfg = build_config(env_file=env)
    assert cfg["llm"]["url"] == "https://env.example/v1/chat/completions"
    assert cfg["llm"]["auth_token"] == "from-env"
    assert cfg["llm"]["model"] == "env-model"

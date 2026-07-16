from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from bake_ocr_config import (
    build_config,
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


def test_build_config_copies_source_as_is(tmp_path: Path):
    cfg_path = tmp_path / "src.json"
    src = {
        "llm": {
            "url": "https://api.example/v1/chat/completions",
            "auth_token": "sk",
            "model": "m",
            "use_anthropic": False,
        },
        "gitlab": {"api_token": "glpat-x"},
    }
    cfg_path.write_text(json.dumps(src), encoding="utf-8")
    assert build_config(config_file=cfg_path) == src
    assert build_config(config_file=cfg_path)["llm"].get("extra_body") is None


def test_build_config_env_file_overrides(tmp_path: Path):
    cfg_path = tmp_path / "base.json"
    env = tmp_path / ".env"
    cfg_path.write_text(
        json.dumps(
            {
                "llm": {
                    "url": "https://old.example/v1/chat/completions",
                    "auth_token": "old",
                    "model": "old-model",
                },
                "gitlab": {"api_token": "old-pat"},
            }
        ),
        encoding="utf-8",
    )
    env.write_text(
        "LLM_API_BASE=https://env.example/v1\nLLM_API_KEY=from-env\nLLM_MODEL=env-model\n",
        encoding="utf-8",
    )
    cfg = build_config(config_file=cfg_path, env_file=env)
    assert cfg["llm"]["url"] == "https://env.example/v1/chat/completions"
    assert cfg["llm"]["auth_token"] == "from-env"
    assert cfg["llm"]["model"] == "env-model"


def test_main_rejects_invalid_json(tmp_path: Path, capsys):
    from bake_ocr_config import main

    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    out = tmp_path / "out.json"
    old_argv = sys.argv
    try:
        sys.argv = ["bake_ocr_config.py", "--config", str(bad), "-o", str(out)]
        with pytest.raises(SystemExit) as exc:
            main()
        assert exc.value.code == 1
    finally:
        sys.argv = old_argv
    assert "failed to load config" in capsys.readouterr().err

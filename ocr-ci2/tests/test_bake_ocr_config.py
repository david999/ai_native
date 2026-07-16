"""bake_ocr_config：直接复制源配置，不做 defaults 合并。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_ACCEPTANCE = Path(__file__).resolve().parents[1] / "scripts" / "acceptance"
if str(_ACCEPTANCE) not in sys.path:
    sys.path.insert(0, str(_ACCEPTANCE))

from bake_ocr_config import build_config, validate_baked_config  # noqa: E402


def test_build_config_copies_source_as_is(tmp_path: Path):
    cfg_path = tmp_path / "prod.json"
    src = {
        "llm": {
            "url": "https://aigateway.aulton.com/v1/chat/completions",
            "auth_token": "sk-test",
            "model": "Aulton-DeepSeek-V4-Flash",
            "use_anthropic": False,
        },
        "gitlab": {"api_token": "glpat-test"},
        "language": "Chinese",
    }
    cfg_path.write_text(json.dumps(src), encoding="utf-8")
    cfg = build_config(config_file=cfg_path)
    assert cfg == src
    assert cfg["llm"].get("extra_body") is None
    assert not validate_baked_config(cfg)


def test_build_config_preserves_extra_body_if_present(tmp_path: Path):
    """源文件写了 extra_body 就原样保留（由调用方负责模型兼容性）。"""
    cfg_path = tmp_path / "glm.json"
    src = {
        "llm": {
            "url": "https://example.com/v1/chat/completions",
            "auth_token": "sk-x",
            "model": "glm",
            "extra_body": {"thinking": {"type": "disabled"}},
        },
        "gitlab": {"api_token": "glpat-x"},
    }
    cfg_path.write_text(json.dumps(src), encoding="utf-8")
    cfg = build_config(config_file=cfg_path)
    assert cfg["llm"]["extra_body"] == {"thinking": {"type": "disabled"}}


def test_env_file_overrides_token(tmp_path: Path):
    cfg_path = tmp_path / "base.json"
    env_path = tmp_path / "secrets.env"
    cfg_path.write_text(
        json.dumps(
            {
                "llm": {
                    "url": "https://aigateway.aulton.com/v1/chat/completions",
                    "auth_token": "old",
                    "model": "Aulton-DeepSeek-V4-Flash",
                },
                "gitlab": {"api_token": "old-pat"},
            }
        ),
        encoding="utf-8",
    )
    env_path.write_text("LLM_API_KEY=new-key\nGITLAB_API_TOKEN=new-pat\n", encoding="utf-8")
    cfg = build_config(config_file=cfg_path, env_file=env_path)
    assert cfg["llm"]["auth_token"] == "new-key"
    assert cfg["gitlab"]["api_token"] == "new-pat"

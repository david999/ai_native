#!/usr/bin/env python3
"""Bake OpenCodeReview 配置为 Docker 镜像用 config.json。

**非自动化测试脚本** — 在 build_image.ps1 构建镜像时执行。
日常 OCR 配置仍放在 ~/.opencodereview/config.json。

用法：
  python scripts/acceptance/bake_ocr_config.py --config deploy/prod/docker/prod.config.json -o .build/config.json
  python scripts/acceptance/bake_ocr_config.py --from-user-config -o .build/config.json

逻辑清单：
- 直接复制用户提供的 config.json（--config / --from-user-config），**不做 defaults 合并**
- 可选 --env-file / --include-process-env：仅覆盖 llm/gitlab 相关密钥字段
- --require-secrets：缺少 llm/gitlab token 时 bake 失败（build_image.ps1 默认开启）
- 不做：安装 OCR CLI；原生 install 直接读 live config.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
from ocr_ci_config import gitlab_api_token_from_config, user_config_path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def llm_url_from_base(base: str) -> str:
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def apply_llm_from_mapping(cfg: dict[str, Any], mapping: dict[str, str]) -> None:
    """用环境变量覆盖 llm 字段（仅当 mapping 中有对应键时）。"""
    llm = cfg.setdefault("llm", {})
    url = mapping.get("OCR_LLM_URL") or ""
    if not url and mapping.get("LLM_API_BASE"):
        url = llm_url_from_base(mapping["LLM_API_BASE"])
    if url:
        llm["url"] = url
    token = (
        mapping.get("OCR_LLM_TOKEN")
        or mapping.get("OCR_LLM_AUTH_TOKEN")
        or mapping.get("LLM_API_KEY")
        or ""
    )
    if token:
        llm["auth_token"] = token
    model = mapping.get("OCR_LLM_MODEL") or mapping.get("LLM_MODEL") or ""
    if model:
        llm["model"] = model
    if mapping.get("OCR_USE_ANTHROPIC"):
        llm["use_anthropic"] = mapping["OCR_USE_ANTHROPIC"].lower() in ("1", "true", "yes")


def apply_gitlab_from_mapping(cfg: dict[str, Any], mapping: dict[str, str]) -> None:
    token = mapping.get("GITLAB_API_TOKEN") or mapping.get("AICR_BOT_TOKEN") or ""
    if token:
        cfg.setdefault("gitlab", {})["api_token"] = token


def load_config_file(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"config must be a JSON object: {path}")
    return data


def build_config(
    *,
    config_file: Path,
    env_file: Path | None = None,
    include_process_env: bool = False,
) -> dict[str, Any]:
    """以 config_file 为唯一基底，可选 env 覆盖密钥字段。"""
    cfg = load_config_file(config_file)
    if env_file:
        env_map = parse_env_file(env_file)
        apply_llm_from_mapping(cfg, env_map)
        apply_gitlab_from_mapping(cfg, env_map)
    if include_process_env:
        apply_llm_from_mapping(cfg, {k: v for k, v in os.environ.items() if v})
        apply_gitlab_from_mapping(cfg, {k: v for k, v in os.environ.items() if v})
    return cfg


def validate_baked_config(cfg: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    llm = cfg.get("llm")
    if not isinstance(llm, dict):
        missing.append("llm")
        return missing
    if not llm.get("url"):
        missing.append("llm.url")
    elif not str(llm["url"]).rstrip("/").endswith("/chat/completions"):
        missing.append("llm.url (must end with /chat/completions)")
    if not llm.get("auth_token"):
        missing.append("llm.auth_token")
    if not llm.get("model"):
        missing.append("llm.model")
    if not gitlab_api_token_from_config(cfg):
        missing.append("gitlab.api_token")
    return missing


def main() -> None:
    parser = argparse.ArgumentParser(description="Bake OCR config.json for ocr-gateway image")
    parser.add_argument("-o", "--output", type=Path, default=_repo_root() / ".build" / "config.json")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--config", type=Path, help="Source config.json (required unless --from-user-config)")
    parser.add_argument("--from-user-config", action="store_true", help="Use ~/.opencodereview/config.json")
    parser.add_argument("--include-process-env", action="store_true")
    parser.add_argument("--require-secrets", action="store_true")
    args = parser.parse_args()

    config_file = args.config
    if args.from_user_config and not config_file:
        config_file = user_config_path()
    if not config_file:
        print("ERROR: provide --config PATH or --from-user-config", file=sys.stderr)
        sys.exit(2)
    if not config_file.is_file():
        print(f"Config not found: {config_file}", file=sys.stderr)
        sys.exit(1)

    cfg = build_config(
        config_file=config_file,
        env_file=args.env_file,
        include_process_env=args.include_process_env,
    )
    if args.require_secrets:
        missing = validate_baked_config(cfg)
        if missing:
            print("Baked config validation failed:", ", ".join(missing), file=sys.stderr)
            sys.exit(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")

    llm = cfg.get("llm", {})
    print(f"Wrote {args.output} (from {config_file})", file=sys.stderr)
    print(
        f"  llm.url={'set' if llm.get('url') else 'unset'}, "
        f"llm.model={llm.get('model') or 'unset'}, "
        f"llm.auth_token={'set' if llm.get('auth_token') else 'unset'}, "
        f"gitlab.api_token={'set' if gitlab_api_token_from_config(cfg) else 'unset'}, "
        f"llm.extra_body={llm.get('extra_body')!r}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()

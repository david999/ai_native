#!/usr/bin/env python3
"""Bake OpenCodeReview ~/.opencodereview/config.json for ocr-ci Docker image.

OCR resolves LLM settings at runtime with priority:
  environment variables  >  ~/.opencodereview/config.json

GitLab MR posting (post_ocr_to_gitlab.py) reads gitlab.api_token from the same file
when GITLAB_API_TOKEN env is unset.

Recommended single source on your PC:
  %USERPROFILE%\\.opencodereview\\config.json

Usage:
  # From user config (default for build_image.ps1)
  python scripts/bake_ocr_config.py --from-user-config -o .build/config.json

  # Defaults only (no secrets)
  python scripts/bake_ocr_config.py -o .build/config.json

  # Optional legacy: merge evn/.env LLM keys
  python scripts/bake_ocr_config.py --env-file ../evn/.env -o .build/config.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from ocr_ci_config import gitlab_api_token_from_config, user_config_path


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_defaults() -> dict[str, Any]:
    """Load config/defaults.config.json (no secrets; extra_body + use_anthropic only)."""
    path = _repo_root() / "config" / "defaults.config.json"
    with path.open(encoding="utf-8") as f:
        return json.load(f)


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
    """Normalize LLM_API_BASE-style roots to OpenAI-compatible chat/completions URL."""
    base = base.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"


def merge_llm_from_mapping(cfg: dict[str, Any], mapping: dict[str, str]) -> None:
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


def merge_gitlab_from_mapping(cfg: dict[str, Any], mapping: dict[str, str]) -> None:
    token = mapping.get("GITLAB_API_TOKEN") or mapping.get("AICR_BOT_TOKEN") or ""
    if token:
        cfg.setdefault("gitlab", {})["api_token"] = token


def deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(base))
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def build_config(
    *,
    env_file: Path | None = None,
    config_file: Path | None = None,
    include_process_env: bool = False,
) -> dict[str, Any]:
    """Merge defaults ← JSON overlay ← optional dotenv / process env (legacy paths)."""
    cfg = load_defaults()
    if config_file:
        with config_file.open(encoding="utf-8") as f:
            overlay = json.load(f)
        cfg = deep_merge(cfg, overlay)
    if env_file:
        env_map = parse_env_file(env_file)
        merge_llm_from_mapping(cfg, env_map)
        merge_gitlab_from_mapping(cfg, env_map)
    if include_process_env:
        merge_llm_from_mapping(cfg, {k: v for k, v in os.environ.items() if v})
    return cfg


def main() -> None:
    # Recommended: --from-user-config → ~/.opencodereview/config.json
    parser = argparse.ArgumentParser(description="Bake OCR config.json for ocr-ci image")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_repo_root() / ".build" / "config.json",
        help="Output path (default: ocr-ci/.build/config.json)",
    )
    parser.add_argument(
        "--env-file",
        type=Path,
        help="Read LLM_* / OCR_LLM_* from dotenv (e.g. ../evn/.env)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Merge a JSON file (default with --from-user-config: ~/.opencodereview/config.json)",
    )
    parser.add_argument(
        "--from-user-config",
        action="store_true",
        help="Merge %USERPROFILE%/.opencodereview/config.json (recommended)",
    )
    parser.add_argument(
        "--include-process-env",
        action="store_true",
        help="Also read OCR_LLM_* / LLM_* from current shell environment",
    )
    args = parser.parse_args()

    config_file = args.config
    if args.from_user_config and not config_file:
        config_file = user_config_path()
        if not config_file.is_file():
            print(f"User config not found: {config_file}", file=sys.stderr)
            sys.exit(1)

    cfg = build_config(
        env_file=args.env_file,
        config_file=config_file,
        include_process_env=args.include_process_env,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
        f.write("\n")

    # Never log secret values; only report set/unset.
    llm = cfg.get("llm", {})
    has_llm_secret = bool(llm.get("auth_token"))
    has_gitlab = bool(gitlab_api_token_from_config(cfg))
    print(f"Wrote {args.output}", file=sys.stderr)
    print(
        f"  llm.url={'set' if llm.get('url') else 'unset'}, "
        f"llm.model={llm.get('model') or 'unset'}, "
        f"llm.auth_token={'set' if has_llm_secret else 'unset'}, "
        f"gitlab.api_token={'set' if has_gitlab else 'unset'}",
        file=sys.stderr,
    )
    print(
        "Note: Job env OCR_LLM_* / GITLAB_API_TOKEN override this file at runtime.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()

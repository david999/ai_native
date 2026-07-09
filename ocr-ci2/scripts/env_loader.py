"""ocr-ci2 共享环境变量加载（E2E、acceptance、live 脚本统一入口）。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

OCR_CI2_ROOT = Path(__file__).resolve().parents[1]
_SCRIPTS = OCR_CI2_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from ocr_ci_config import resolve_gitlab_api_token  # noqa: E402

_TOKEN_KEYS = ("AICR_BOT_TOKEN", "ROOT_PAT", "GITLAB_API_TOKEN")


def _parse_env_file(path: Path, *, override: bool = False) -> None:
    """将 KEY=VALUE 行写入 os.environ；默认不覆盖已有进程环境变量。"""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if not key or not val or val.startswith("..."):
            continue
        if override or key not in os.environ:
            os.environ[key] = val


def _candidate_env_files() -> list[Path]:
    """按优先级列出可选 .env 文件（显式 OCR_CI2_ENV_FILE 时仅用该文件）。"""
    explicit = os.environ.get("OCR_CI2_ENV_FILE", "").strip()
    if explicit:
        return [Path(explicit).expanduser()]
    candidates: list[Path] = [OCR_CI2_ROOT / ".env"]
    # monorepo 内可回退 evn/.env；独立 checkout 无此路径则跳过
    monorepo = OCR_CI2_ROOT.parent
    if (monorepo / "evn" / ".env").is_file():
        candidates.append(monorepo / "evn" / ".env")
    return candidates


def load_dotenv(*, env_file: str | None = None, override: bool = False) -> None:
    """加载 GitLab token 等；优先进程 env，其次 env 文件与 config.json。"""
    if env_file:
        _parse_env_file(Path(env_file).expanduser(), override=True)
    else:
        for path in _candidate_env_files():
            _parse_env_file(path, override=override)

    if not os.environ.get("GITLAB_API_TOKEN"):
        token = resolve_gitlab_api_token()
        if token:
            os.environ.setdefault("GITLAB_API_TOKEN", token)


def resolve_gitlab_token() -> str:
    """与 Python E2E / PowerShell print_gitlab_token.py 一致的 token 解析顺序。"""
    load_dotenv()
    for key in _TOKEN_KEYS:
        val = os.environ.get(key, "").strip()
        if val:
            return val
    return resolve_gitlab_api_token() or ""

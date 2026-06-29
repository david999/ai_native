"""Gateway 运行时配置（环境变量优先于默认值）。

逻辑清单：
- 解析：POST_SCRIPT、WORK_ROOT、GitLab URL（env + 仓库/Docker 启发式）
- gateway_secret()：每次请求时读取（便于测试 monkeypatch）
- validate_project_id()：仅允许数字 GitLab project id
- ocr_review_supports_flag()：探测已安装 ocr CLI 是否支持某 review 参数
- 不做：import 时校验 ocr 是否在 PATH；不重启进程即热重载 env
"""

from __future__ import annotations

import functools
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

_PROJECT_ID_RE = re.compile(r"^[0-9]+$")
_REPO_ROOT = Path(__file__).resolve().parent.parent


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _env_bool(name: str, default: str = "") -> bool:
    return _env(name, default).lower() in ("1", "true", "yes")


def _default_post_script() -> str:
    env_val = _env("OCR_POST_SCRIPT")
    if env_val:
        return env_val
    repo_script = _REPO_ROOT / "scripts" / "post_ocr_to_gitlab.py"
    if repo_script.is_file():
        return str(repo_script.resolve())
    return "/usr/local/lib/ocr-ci/post_ocr_to_gitlab.py"


def _default_work_root() -> str:
    env_val = _env("OCR_GATEWAY_WORK_ROOT")
    if env_val:
        return env_val
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA", "")
        if local:
            return str(Path(local) / "ocr-gateway" / "work")
    repo_work = _REPO_ROOT / ".gateway-work"
    return str(repo_work.resolve())


def _default_gitlab_internal_url() -> str:
    if _env("OCR_GATEWAY_GITLAB_URL"):
        return _env("OCR_GATEWAY_GITLAB_URL")
    # Native on host: GitLab usually localhost; Docker gateway uses gitlab:8000
    if (_REPO_ROOT / "scripts" / "post_ocr_to_gitlab.py").is_file() and not Path(
        "/.dockerenv"
    ).exists():
        return "http://localhost:8000"
    return "http://gitlab:8000"


GITLAB_INTERNAL_URL: str = _default_gitlab_internal_url()
GITLAB_PUBLIC_URL: str = _env("OCR_GATEWAY_GITLAB_PUBLIC_URL", "http://localhost:8000")
GITLAB_API_URL: str = _env("OCR_GATEWAY_GITLAB_API_URL") or GITLAB_INTERNAL_URL


def gateway_secret() -> str:
    """每次请求时读取，便于测试 monkeypatch 环境变量。"""
    return _env("OCR_GATEWAY_SECRET", "")


def mr_progress_notes_enabled() -> bool:
    """为 false（默认）时不向 MR 发送 queued/running 进度 note。"""
    return _env_bool("OCR_GATEWAY_MR_NOTES")


POST_SCRIPT: str = _default_post_script()
WORK_ROOT: str = _default_work_root()
MAX_CONCURRENT: int = max(1, int(_env("OCR_GATEWAY_MAX_CONCURRENT", "2") or "2"))
OCR_CONCURRENCY: str = _env("OCR_REVIEW_CONCURRENCY", "4")
OCR_REVIEW_EXCLUDE: str = _env("OCR_REVIEW_EXCLUDE")
OCR_REVIEW_MAX_TOOLS: str = _env("OCR_REVIEW_MAX_TOOLS")
WORKSPACE_MAX_MIRRORS: int = max(0, int(_env("OCR_GATEWAY_WORKSPACE_MAX_PROJECTS", "0") or "0"))
MAX_JOB_HISTORY: int = max(50, int(_env("OCR_GATEWAY_MAX_JOB_HISTORY", "500") or "500"))
GATEWAY_PORT: int = max(1, int(_env("OCR_GATEWAY_PORT", "8010") or "8010"))


def validate_project_id(project_id: str) -> None:
    """拒绝路径穿越；GitLab project id 须为纯数字。"""
    if not _PROJECT_ID_RE.fullmatch(project_id):
        raise ValueError(f"invalid project_id (expected numeric GitLab id): {project_id!r}")


def validate_job_id(job_id: str) -> None:
    if not job_id or "/" in job_id or "\\" in job_id or ".." in job_id:
        raise ValueError(f"invalid job_id: {job_id!r}")


def job_artifact_paths(job_id: str) -> tuple[Path, Path]:
    """ocr review 输出路径（Windows 无 /tmp，统一落在 WORK_ROOT 下）。"""
    validate_job_id(job_id)
    custom = _env("OCR_GATEWAY_TMP_DIR")
    base = Path(custom) if custom else Path(WORK_ROOT) / "job-artifacts"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"ocr-result-{job_id}.json", base / f"ocr-stderr-{job_id}.log"


def resolve_executable(name: str) -> str:
    """Windows 上 npm 全局命令多为 .cmd，subprocess 需完整路径。"""
    path = shutil.which(name)
    if not path:
        raise FileNotFoundError(
            f"{name} not found in PATH; install OpenCodeReview CLI (npm install -g @alibaba-group/open-code-review)"
        )
    return path


@functools.lru_cache(maxsize=8)
def ocr_review_supports_flag(flag: str) -> bool:
    """Return True if ``ocr review --help`` lists *flag* (e.g. ``--exclude``)."""
    needle = flag.strip()
    if not needle:
        return False
    try:
        exe = resolve_executable("ocr")
        result = subprocess.run(
            [exe, "review", "--help"],
            capture_output=True,
            timeout=15,
            encoding="utf-8",
            errors="replace",
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False
    text = (result.stdout or "") + (result.stderr or "")
    return needle in text


_SUBPROCESS_TEXT_KW = {"text": True, "encoding": "utf-8", "errors": "replace"}
SUBPROCESS_TEXT_KW = _SUBPROCESS_TEXT_KW

"""Re-export：acceptance 脚本从此目录 import env_loader。"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from env_loader import load_dotenv, resolve_gitlab_token  # noqa: F401

__all__ = ["load_dotenv", "resolve_gitlab_token"]

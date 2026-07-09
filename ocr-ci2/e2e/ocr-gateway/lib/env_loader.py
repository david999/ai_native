"""Re-export：E2E 从此处 import，实现位于 scripts/env_loader.py。"""

from __future__ import annotations

import sys
from pathlib import Path

OCR_CI2_ROOT = Path(__file__).resolve().parents[3]
_SCRIPTS = OCR_CI2_ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from env_loader import load_dotenv, resolve_gitlab_token  # noqa: F401

__all__ = ["load_dotenv", "resolve_gitlab_token"]

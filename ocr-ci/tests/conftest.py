"""Pytest path setup for ocr-ci scripts."""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent / "scripts"
ACCEPTANCE = SCRIPTS / "acceptance"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
if str(ACCEPTANCE) not in sys.path:
    sys.path.insert(0, str(ACCEPTANCE))

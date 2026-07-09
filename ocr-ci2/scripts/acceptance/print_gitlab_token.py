#!/usr/bin/env python3
"""Print GitLab API token to stdout（供 verify_gateway_runner.ps1 与 shell 脚本复用）。"""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1]
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from env_loader import load_dotenv, resolve_gitlab_token  # noqa: E402


def main() -> int:
    load_dotenv()
    token = resolve_gitlab_token()
    if not token:
        return 1
    print(token, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

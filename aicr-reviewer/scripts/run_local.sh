#!/usr/bin/env bash
# 本地启动 aicr-reviewer（无需 Docker）
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v python3 &>/dev/null; then
  echo "python3 not found" >&2
  exit 1
fi

VENV="$ROOT/.venv"
if [[ ! -d "$VENV" ]]; then
  python3 -m venv "$VENV"
fi
# shellcheck disable=SC1091
source "$VENV/bin/activate"
pip install -q -r requirements.txt

export GITLAB_URL="${GITLAB_URL:-http://localhost:8000}"
echo "Starting AICR Reviewer at http://localhost:8001 (GITLAB_URL=$GITLAB_URL)"
exec python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload

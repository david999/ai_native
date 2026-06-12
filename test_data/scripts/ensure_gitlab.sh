#!/usr/bin/env bash
# 探测并在需要时启动本地 GitLab（不使用 Docker）
set -euo pipefail

URL="${GITLAB_URL:-http://localhost:8000}"
NO_START=0
MAX_ATTEMPTS=36
INTERVAL=10

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-start) NO_START=1; shift ;;
    --url) URL="$2"; shift 2 ;;
    *) shift ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
START_SCRIPT="$SCRIPT_DIR/start_gitlab.sh"
ENV_FILE="$REPO_ROOT/evn/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$' || true)
  set +a
fi

gitlab_ready() {
  curl -sf -o /dev/null --max-time 8 "$URL" 2>/dev/null
}

echo "Checking GitLab at $URL (no Docker)"
if gitlab_ready; then
  echo "GitLab ready at $URL"
  exit 0
fi

if [[ "$NO_START" -eq 1 ]]; then
  echo "GitLab not ready (-no-start)." >&2
  exit 1
fi

if [[ -x "$START_SCRIPT" ]]; then
  echo "Invoking start_gitlab.sh ..."
  bash "$START_SCRIPT"
else
  echo "No GitLab start script at $START_SCRIPT" >&2
  echo "Set GITLAB_START_COMMAND or create evn/gitlab/start.sh" >&2
  exit 1
fi

for i in $(seq 1 "$MAX_ATTEMPTS"); do
  if gitlab_ready; then
    echo "GitLab ready at $URL (attempt $i)"
    exit 0
  fi
  echo "Waiting for GitLab... ($i/$MAX_ATTEMPTS)"
  sleep "$INTERVAL"
done

echo "GitLab still not ready at $URL." >&2
exit 1

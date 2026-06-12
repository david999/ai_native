#!/usr/bin/env bash
# 启动本机 GitLab（不使用 Docker）
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
HOOK="$REPO_ROOT/evn/gitlab/start.sh"
ENV_FILE="$REPO_ROOT/evn/.env"

if [[ -f "$ENV_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source <(grep -v '^\s*#' "$ENV_FILE" | grep -v '^\s*$' || true)
  set +a
fi

if [[ -n "${GITLAB_START_COMMAND:-}" ]]; then
  echo "Running GITLAB_START_COMMAND..."
  eval "$GITLAB_START_COMMAND"
  exit 0
fi

if [[ -x "$HOOK" ]]; then
  echo "Running $HOOK ..."
  exec "$HOOK"
fi

if command -v systemctl >/dev/null 2>&1; then
  if systemctl list-units --type=service --all 2>/dev/null | grep -qi gitlab; then
    sudo systemctl start gitlab-runsvdir.service 2>/dev/null || true
    exit 0
  fi
fi

echo "No GitLab start method configured." >&2
echo "Set GITLAB_START_COMMAND or create $HOOK" >&2
exit 1

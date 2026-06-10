#!/usr/bin/env bash
# 探测并在需要时通过 Docker Compose 启动本地 GitLab（L3 用）
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
COMPOSE_DIR="$REPO_ROOT/evn/gitlab"

gitlab_ready() {
  curl -sf -o /dev/null --max-time 8 "$URL" 2>/dev/null
}

echo "Checking GitLab at $URL"
if gitlab_ready; then
  echo "GitLab ready at $URL"
  exit 0
fi

if [[ "$NO_START" -eq 1 ]]; then
  echo "GitLab not ready (-no-start: will not start Docker)." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "GitLab not reachable and docker CLI not found." >&2
  echo "Install Docker or start GitLab manually at $URL" >&2
  exit 1
fi

echo "Starting GitLab via Docker Compose ($COMPOSE_DIR)..."
docker network inspect gitlab_default >/dev/null 2>&1 || docker network create gitlab_default
(cd "$COMPOSE_DIR" && docker compose up -d gitlab)
echo "GitLab container starting (first boot may take several minutes)..."

for i in $(seq 1 "$MAX_ATTEMPTS"); do
  if gitlab_ready; then
    echo "GitLab ready at $URL (attempt $i)"
    exit 0
  fi
  echo "Waiting for GitLab... ($i/$MAX_ATTEMPTS)"
  sleep "$INTERVAL"
done

echo "GitLab still not ready at $URL after docker compose up." >&2
echo "Check: docker logs gitlab" >&2
exit 1

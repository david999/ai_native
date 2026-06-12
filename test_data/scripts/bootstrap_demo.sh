#!/usr/bin/env bash
# 校验 spring-cloud-demo 存在且 remote 指向本地 GitLab
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DEMO_DIR="$REPO_ROOT/test_data/spring-cloud-demo"
GITLAB_URL="${GITLAB_URL:-http://localhost:8000}"

if [[ ! -d "$DEMO_DIR" ]]; then
  echo "spring-cloud-demo not found at $DEMO_DIR — clone from $GITLAB_URL first" >&2
  exit 1
fi

cd "$DEMO_DIR"
remote="$(git remote get-url origin 2>/dev/null || true)"
if [[ -z "$remote" ]]; then
  echo "No git remote 'origin' in spring-cloud-demo" >&2
  exit 1
fi
if [[ "$remote" != *":8000"* && "$remote" != *"localhost:8000"* ]]; then
  echo "Warning: origin may not point to local GitLab: $remote"
fi
echo "OK demo remote: $remote"

if git rev-parse --verify aicr-test-base >/dev/null 2>&1; then
  echo "OK baseline branch aicr-test-base exists"
else
  current="$(git branch --show-current || true)"
  if [[ -z "$current" ]]; then
    git checkout -B main 2>/dev/null || true
  fi
  git checkout -B aicr-test-base
  git push -u origin aicr-test-base 2>/dev/null || true
  echo "Created baseline branch aicr-test-base"
fi

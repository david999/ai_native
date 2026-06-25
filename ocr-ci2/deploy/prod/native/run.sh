#!/usr/bin/env bash
# 在宿主机运行 OCR Gateway — 生产原生（Linux）
#
# 逻辑清单：
# - 加载：deploy/prod/native/gateway.env（或第一个参数指定路径）
# - 校验：OCR_GATEWAY_SECRET 必填
# - 默认：PYTHONPATH=仓库根、OCR_POST_SCRIPT、WORK_ROOT=/var/ocr-gateway/work
# - 不做：校验 ocr 是否在 PATH；systemd 集成；守护进程（请用 systemd unit）

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
DEPLOY_NATIVE="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="${1:-$DEPLOY_NATIVE/gateway.env}"

if [[ -f "$ENV_FILE" ]]; then
  echo "Loading env from $ENV_FILE"
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
else
  echo "WARNING: No $ENV_FILE — see deploy/prod/native/gateway.env.example" >&2
fi

if [[ -z "${OCR_GATEWAY_SECRET:-}" ]]; then
  echo "OCR_GATEWAY_SECRET is required in $ENV_FILE" >&2
  exit 1
fi

export PYTHONPATH="$ROOT"
export OCR_POST_SCRIPT="${OCR_POST_SCRIPT:-$ROOT/scripts/post_ocr_to_gitlab.py}"
export OCR_GATEWAY_WORK_ROOT="${OCR_GATEWAY_WORK_ROOT:-/var/ocr-gateway/work}"
PORT="${OCR_GATEWAY_PORT:-8010}"

echo "Starting OCR Gateway on http://0.0.0.0:${PORT}"
echo "Health: http://localhost:${PORT}/health"

cd "$ROOT"
exec python3 -m uvicorn gateway.main:app --host 0.0.0.0 --port "$PORT"

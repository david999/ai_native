#!/usr/bin/env bash
# 生产环境原生安装（Linux）
#
# 逻辑清单：
# - 校验：node、npm、python3、git 在 PATH 上（缺失则退出）
# - OCR CLI：`ocr version` 成功则跳过 `npm install -g`（除非 SKIP_OCR_NPM=1）
# - 始终：pip install -r gateway/requirements.txt
# - 仅警告：缺少 ~/.opencodereview/config.json（不阻断）
# - 不做：校验 npm 包版本；跳过 pip install；创建 config.json

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
SKIP_OCR_NPM="${SKIP_OCR_NPM:-0}"

require_cmd() {
  command -v "$1" >/dev/null 2>&1 || { echo "Missing command: $1" >&2; exit 1; }
}

ocr_cli_installed() {
  command -v ocr >/dev/null 2>&1 && ocr version >/dev/null 2>&1
}

echo "Checking prerequisites..."
require_cmd node
require_cmd npm
require_cmd python3
require_cmd git

if [[ "$SKIP_OCR_NPM" != "1" ]]; then
  if ocr_cli_installed; then
    echo "OpenCodeReview CLI already installed; skipping npm install -g"
  else
    echo "Installing OpenCodeReview CLI (global npm)..."
    npm install -g @alibaba-group/open-code-review
  fi
fi

echo "Installing Gateway Python deps..."
python3 -m pip install -r "$ROOT/gateway/requirements.txt"

USER_CFG="${HOME}/.opencodereview/config.json"
if [[ ! -f "$USER_CFG" ]]; then
  echo "WARNING: Missing $USER_CFG — create llm.* and gitlab.api_token before reviews." >&2
fi

echo "OCR CLI:"
ocr version || true
echo ""
echo "Next: cp deploy/prod/native/gateway.env.example deploy/prod/native/gateway.env"
echo "      ./deploy/prod/native/run.sh"

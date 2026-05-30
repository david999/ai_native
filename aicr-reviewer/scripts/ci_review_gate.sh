#!/usr/bin/env bash
# GitLab Runner 调用 AICR /review，仅在「真实评审完成且分数低于阈值」时失败。
# 网络/HTTP/鉴权/服务异常等一律放行 MR。
#
# 必需环境变量:
#   AICR_REVIEW_URL     例如 http://aicr-reviewer:8001
#   CI_PROJECT_ID       GitLab 自动注入（或设 AICR_PROJECT_ID）
#   CI_MERGE_REQUEST_IID
#
# 可选:
#   AICR_REVIEW_SECRET  → Header X-AICR-Secret
#   AICR_SCORE_THRESHOLD  默认 60

set -uo pipefail

THRESHOLD="${AICR_SCORE_THRESHOLD:-60}"
URL="${AICR_REVIEW_URL:?set AICR_REVIEW_URL}"
PROJECT_ID="${CI_PROJECT_ID:-${AICR_PROJECT_ID:?set CI_PROJECT_ID or AICR_PROJECT_ID}}"
MR_IID="${CI_MERGE_REQUEST_IID:-${AICR_MR_IID:?set CI_MERGE_REQUEST_IID or AICR_MR_IID}}"

pass_job() {
  echo "AICR gate: MR passes — $*"
  exit 0
}

fail_job() {
  echo "AICR gate: MR blocked — $*"
  exit 1
}

if ! command -v jq >/dev/null 2>&1; then
  pass_job "jq not installed, skip gate"
fi

BODY=$(jq -n --argjson project_id "$PROJECT_ID" --argjson mr_iid "$MR_IID" \
  '{project_id: $project_id, mr_iid: $mr_iid}')

CURL_ARGS=(-sS -m "${AICR_REVIEW_TIMEOUT:-300}" -w "\n%{http_code}" \
  -H "Content-Type: application/json" -d "$BODY")
if [[ -n "${AICR_REVIEW_SECRET:-}" ]]; then
  CURL_ARGS+=(-H "X-AICR-Secret: ${AICR_REVIEW_SECRET}")
fi

RESP_FILE=$(mktemp)
trap 'rm -f "$RESP_FILE"' EXIT

if ! CURL_OUT=$(curl "${CURL_ARGS[@]}" "${URL%/}/review" 2>&1); then
  pass_job "request failed: ${CURL_OUT}"
fi

HTTP_CODE=$(echo "$CURL_OUT" | tail -n1)
RESP_BODY=$(echo "$CURL_OUT" | sed '$d')

if [[ "$HTTP_CODE" != "200" ]]; then
  pass_job "HTTP ${HTTP_CODE}"
fi

echo "$RESP_BODY" >"$RESP_FILE"
if ! jq -e . "$RESP_FILE" >/dev/null 2>&1; then
  pass_job "invalid JSON response"
fi

COMPLETED=$(jq -r '.review_completed // false' "$RESP_FILE")
SCORE=$(jq -r '.score // empty' "$RESP_FILE")
SUMMARY=$(jq -r '.summary // ""' "$RESP_FILE")

echo "AICR response: review_completed=${COMPLETED} score=${SCORE}"
[[ -n "$SUMMARY" ]] && echo "$SUMMARY"

if [[ "$COMPLETED" != "true" ]]; then
  pass_job "review not completed"
fi

if [[ -z "$SCORE" ]]; then
  pass_job "missing score"
fi

if python3 -c "import sys; sys.exit(0 if float('${SCORE}') < float('${THRESHOLD}') else 1)"; then
  fail_job "score ${SCORE} < threshold ${THRESHOLD}"
fi

pass_job "score ${SCORE} >= threshold ${THRESHOLD}"

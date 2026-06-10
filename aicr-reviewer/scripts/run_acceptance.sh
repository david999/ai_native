#!/usr/bin/env bash
# Linux/macOS acceptance (default daily=L1+L2, no Docker)
set -euo pipefail

LEVEL="${1:-daily}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AICR_ROOT="$REPO_ROOT/aicr-reviewer"
TS="$(date -u +%Y-%m-%dT%H%M%S)"
RECORD_DIR="${RECORD_DIR:-$REPO_ROOT/test-results/$TS}"
mkdir -p "$RECORD_DIR"

echo "Acceptance run: $RECORD_DIR (level=$LEVEL)"

cd "$AICR_ROOT"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
PY=".venv/bin/python"

should_run() {
  case "$LEVEL" in
    daily) [[ "$1" == "L1" || "$1" == "L2" ]] ;;
    all) return 0 ;;
    *) [[ "$LEVEL" == "$1" ]] ;;
  esac
}

FAILED=0
L3_SKIPPED=0

if should_run L1; then
  echo "=== L1 smoke ==="
  "$PY" scripts/smoke_test.py --report-json "$RECORD_DIR/l1-smoke.json"
fi

if should_run L2; then
  echo "=== L2 health ==="
  if ! curl -sf http://localhost:8001/health >/dev/null 2>&1; then
    echo "Start AICR first: ./scripts/run_local.sh"
  fi
  if ! "$PY" scripts/health_check.py --report-json "$RECORD_DIR/l2-health.json"; then
    FAILED=1
  fi
fi

if should_run L3; then
  echo "=== L3 E2E (GitLab must be running) ==="
  mkdir -p "$RECORD_DIR/l3"
  if ! bash "$REPO_ROOT/test_data/scripts/ensure_gitlab.sh"; then
    L3_SKIPPED=1
    if [[ "$LEVEL" == "L3" ]]; then
      FAILED=1
    else
      echo "L3 skipped: GitLab not ready"
    fi
  else
    SCENARIO="${SCENARIO:-S02_npe_optional}"
    "$PY" "$REPO_ROOT/test_data/scripts/apply_scenario.py" \
      --scenario "$SCENARIO" --report-json "$RECORD_DIR/l3/apply.json"
    # MR + matrix steps can be extended here
  fi
fi

ARGS=(scripts/report_zh.py --record-dir "$RECORD_DIR" --level "$LEVEL")
[[ "$FAILED" -eq 1 ]] && ARGS+=(--failed)
"$PY" "${ARGS[@]}"

cat >"$RECORD_DIR/summary.json" <<EOF
{"level":"$LEVEL","record_dir":"$RECORD_DIR","failed":$FAILED,"l3_skipped":$L3_SKIPPED}
EOF
echo "Done: $RECORD_DIR"
[[ "$FAILED" -eq 1 ]] && exit 1
exit 0

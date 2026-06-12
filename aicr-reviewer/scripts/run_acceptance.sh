#!/usr/bin/env bash
# Linux/macOS acceptance (default daily=L1+L2, no Docker)
set -euo pipefail

LEVEL="${1:-daily}"
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
AICR_ROOT="$REPO_ROOT/aicr-reviewer"
TS="$(date -u +%Y-%m-%dT%H%M%S)"
RECORD_DIR="${RECORD_DIR:-$REPO_ROOT/test-results/$TS}"
SCENARIO="${SCENARIO:-S02_npe_optional}"
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

ensure_aicr_for_l3() {
  "$PY" - <<'PY'
import json
import os
import sys
import urllib.request

from app.env_loader import apply_monorepo_env

apply_monorepo_env()
try:
    with urllib.request.urlopen("http://localhost:8001/health/detail", timeout=5) as resp:
        detail = json.loads(resp.read().decode())
except OSError:
    print("AICR not reachable at http://localhost:8001", file=sys.stderr)
    sys.exit(1)

if not detail.get("llm_key_set"):
    print("LLM_API_KEY not visible to AICR", file=sys.stderr)
    sys.exit(1)

if detail.get("review_auth_required"):
    if not os.environ.get("REVIEW_API_SECRET", "").strip():
        print("REVIEW_API_SECRET required for /review", file=sys.stderr)
        sys.exit(1)
elif not detail.get("review_api_allow_insecure"):
    print("Set REVIEW_API_ALLOW_INSECURE=1 or REVIEW_API_SECRET", file=sys.stderr)
    sys.exit(1)
PY
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
  echo "=== L3 E2E (GitLab + LLM) ==="
  mkdir -p "$RECORD_DIR/l3"
  if ! ensure_aicr_for_l3; then
    FAILED=1
  elif ! bash "$REPO_ROOT/test_data/scripts/ensure_gitlab.sh"; then
    L3_SKIPPED=1
    if [[ "$LEVEL" == "L3" ]]; then
      FAILED=1
    else
      echo "L3 skipped: GitLab not ready"
    fi
  else
    bash "$REPO_ROOT/test_data/scripts/bootstrap_demo.sh"
    if ! "$PY" "$REPO_ROOT/test_data/scripts/apply_scenario.py" \
      --scenario "$SCENARIO" --report-json "$RECORD_DIR/l3/apply.json"; then
      FAILED=1
    else
      branch="$("$PY" -c "import json; print(json.load(open('$RECORD_DIR/l3/apply.json'))['scenarios'][0]['branch'])")"
      scenario_id="$("$PY" -c "import json; print(json.load(open('$RECORD_DIR/l3/apply.json'))['scenarios'][0]['scenario_id'])")"
      if ! "$PY" "$REPO_ROOT/test_data/scripts/create_or_update_mr.py" \
        --source-branch "$branch" --target-branch main \
        --title "AICR acceptance $scenario_id" --report-json "$RECORD_DIR/l3/mr.json"; then
        FAILED=1
      else
        project_id="$("$PY" -c "import json; print(json.load(open('$RECORD_DIR/l3/mr.json'))['project_id'])")"
        mr_iid="$("$PY" -c "import json; print(json.load(open('$RECORD_DIR/l3/mr.json'))['mr_iid'])")"
        matrix_dir="$RECORD_DIR/l3/$scenario_id"
        if ! "$PY" scripts/prompt_matrix_test.py \
          --project-id "$project_id" --mr-iid "$mr_iid" \
          --scenario-id "$scenario_id" --output-dir "$matrix_dir" --force-full; then
          echo "L3 matrix failed: one or more templates did not complete review." >&2
          FAILED=1
        fi
      fi
    fi
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

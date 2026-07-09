"""OCR E2E unit tests (no live GitLab/Gateway)."""

from __future__ import annotations

import sys
from pathlib import Path

E2E_ROOT = Path(__file__).resolve().parents[1]
if str(E2E_ROOT) not in sys.path:
    sys.path.insert(0, str(E2E_ROOT))

from assert_ocr_publish import collect_ocr_content, note_is_ocr
from lib.scenario_manifest import load_index, load_scenario_ids
from poll_gateway_job import parse_gateway_job_id

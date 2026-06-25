"""Load OCR E2E scenario manifests."""

from __future__ import annotations

from pathlib import Path

import yaml

E2E_ROOT = Path(__file__).resolve().parents[1]
SCENARIOS_ROOT = E2E_ROOT / "scenarios"
INDEX_PATH = SCENARIOS_ROOT / "manifest.yaml"


def load_index() -> list[dict]:
    with open(INDEX_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return list(data.get("scenarios") or [])


def load_scenario_ids(all_flag: bool, scenario: str | None) -> list[str]:
    ids = [s["id"] for s in load_index()]
    if all_flag:
        return ids
    if scenario:
        if scenario not in ids:
            raise SystemExit(f"Unknown scenario: {scenario}")
        return [scenario]
    raise SystemExit("Specify --scenario ID or --all")


def get_scenario_spec(scenario_id: str) -> dict:
    for spec in load_index():
        if spec.get("id") == scenario_id:
            return spec
    raise SystemExit(f"Unknown scenario in index: {scenario_id}")


def get_scenario_dir(scenario_id: str) -> Path:
    return SCENARIOS_ROOT / scenario_id

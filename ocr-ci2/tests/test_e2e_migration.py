"""E2E 迁移布局与 paths/env_loader 冒烟测试。"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
E2E_ROOT = REPO_ROOT / "e2e" / "ocr-gateway"

E2E_LAYOUT_FILES = [
    "e2e/ocr-gateway/lib/paths.py",
    "e2e/ocr-gateway/lib/env_loader.py",
    "e2e/ocr-gateway/apply_scenario.py",
    "e2e/ocr-gateway/run_e2e.py",
    "scripts/env_loader.py",
    "scripts/acceptance/verify_gateway_runner.ps1",
    "scripts/acceptance/print_gitlab_token.py",
    "scripts/acceptance/create_or_update_mr.py",
]


def _import_paths():
    if str(E2E_ROOT) not in sys.path:
        sys.path.insert(0, str(E2E_ROOT))
    from lib.paths import OCR_CI2_ROOT, get_datacalc_dir, get_results_root

    return OCR_CI2_ROOT, get_datacalc_dir, get_results_root


def test_e2e_migration_layout_files_exist():
    missing = [rel for rel in E2E_LAYOUT_FILES if not (REPO_ROOT / rel).is_file()]
    assert not missing, f"missing migration files: {missing}"


def test_get_datacalc_dir_default(monkeypatch):
    monkeypatch.delenv("OCR_E2E_DATACALC_DIR", raising=False)
    ocr_root, get_datacalc_dir, _ = _import_paths()
    assert get_datacalc_dir() == ocr_root / "e2e" / "fixtures" / "datacalc-web"


def test_get_results_root_default(monkeypatch):
    monkeypatch.delenv("OCR_E2E_RESULTS_DIR", raising=False)
    ocr_root, _, get_results_root = _import_paths()
    assert get_results_root() == ocr_root / "test-results"


def test_get_datacalc_dir_env_override(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("OCR_E2E_DATACALC_DIR", str(tmp_path))
    _, get_datacalc_dir, _ = _import_paths()
    assert get_datacalc_dir() == tmp_path.resolve()


def test_env_loader_respects_existing_env(monkeypatch, tmp_path: Path):
    env_file = tmp_path / "test.env"
    env_file.write_text("AICR_BOT_TOKEN=from-file\n", encoding="utf-8")

    monkeypatch.setenv("AICR_BOT_TOKEN", "from-process")
    from env_loader import _parse_env_file

    _parse_env_file(env_file, override=False)
    assert os.environ["AICR_BOT_TOKEN"] == "from-process"


def test_env_loader_env_file_overrides(monkeypatch, tmp_path: Path):
    env_file = tmp_path / "override.env"
    env_file.write_text("AICR_BOT_TOKEN=from-override\n", encoding="utf-8")

    monkeypatch.setenv("AICR_BOT_TOKEN", "old")
    from env_loader import load_dotenv

    load_dotenv(env_file=str(env_file))
    assert os.environ["AICR_BOT_TOKEN"] == "from-override"

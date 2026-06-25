"""可选 monorepo 集成测试：ocr-ci2/scripts/gitlab_mr.py 与 ocr-ci 副本一致。

仅在 ai_native 全量 checkout 且存在 ocr-ci/ 时运行；否则 skip。
说明见 docs/测试与验收.md §2。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def monorepo_root() -> Path:
    # tests/ -> ocr-ci2/ -> ai_native/
    return Path(__file__).resolve().parents[2]


def test_gitlab_mr_py_matches_ocr_ci(monorepo_root: Path):
    ci2 = monorepo_root / "ocr-ci2" / "scripts" / "gitlab_mr.py"
    ci = monorepo_root / "ocr-ci" / "scripts" / "gitlab_mr.py"
    if not ci.is_file():
        pytest.skip("ocr-ci/ not present (standalone ocr-ci2 checkout)")
    assert ci2.is_file(), f"missing {ci2}"
    assert _sha256(ci2) == _sha256(ci), "ocr-ci and ocr-ci2 gitlab_mr.py must stay identical"

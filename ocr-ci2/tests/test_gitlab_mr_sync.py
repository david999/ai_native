"""同步检查：ocr-ci2/scripts/gitlab_mr.py 与 ocr-ci 副本一致。

覆盖：ocr-ci 与 ocr-ci2 共享脚本字节级相同。
不测：GitLab API 功能。
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_gitlab_mr_py_matches_ocr_ci():
    repo_root = Path(__file__).resolve().parents[2]
    ci2 = repo_root / "ocr-ci2" / "scripts" / "gitlab_mr.py"
    ci = repo_root / "ocr-ci" / "scripts" / "gitlab_mr.py"
    assert ci2.is_file(), f"missing {ci2}"
    assert ci.is_file(), f"missing {ci}"
    assert _sha256(ci2) == _sha256(ci), "ocr-ci and ocr-ci2 gitlab_mr.py must stay identical"

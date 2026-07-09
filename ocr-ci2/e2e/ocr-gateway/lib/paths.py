"""ocr-ci2 E2E 路径常量（相对 ocr-ci2 根，非 monorepo）。"""

from __future__ import annotations

import os
from pathlib import Path

# e2e/ocr-gateway/lib -> e2e/ocr-gateway
E2E_ROOT = Path(__file__).resolve().parents[1]
# ocr-ci2 仓库根
OCR_CI2_ROOT = Path(__file__).resolve().parents[2]


def get_datacalc_dir() -> Path:
    """样例 Java 仓路径；可用 OCR_E2E_DATACALC_DIR 覆盖 submodule 默认位置。"""
    raw = os.environ.get("OCR_E2E_DATACALC_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return OCR_CI2_ROOT / "e2e" / "fixtures" / "datacalc-web"


def get_results_root() -> Path:
    """E2E 报告根目录，默认 ocr-ci2/test-results。"""
    raw = os.environ.get("OCR_E2E_RESULTS_DIR", "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    return OCR_CI2_ROOT / "test-results"

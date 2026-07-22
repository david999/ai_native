"""Pytest 路径设置：将仓库根与 scripts/ 加入 sys.path。"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(ROOT))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

# 方案 A HTMX 单测默认关闭 SPA，避免 viewer-spa/dist 存在时 / 被 SPA 接管。
# 方案 C 套件（test_dashboard_spa.py）会自行 setenv + reload。
os.environ.setdefault("OCR_DASHBOARD_SPA", "0")

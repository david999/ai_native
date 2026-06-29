"""build_ocr_review_argv 单元测试。"""

from __future__ import annotations

import importlib
import os


def _reload_gateway():
    import gateway.config as cfg
    import gateway.review_service as rs

    importlib.reload(cfg)
    return importlib.reload(rs)


def _sample_request():
    from gateway.review_service import ReviewRequest

    return ReviewRequest(
        project_id="1",
        project_path="group/proj",
        mr_iid="7",
        target_branch="main",
        commit_sha="abc123",
    )


def test_build_ocr_review_argv_base():
    os.environ.pop("OCR_REVIEW_EXCLUDE", None)
    os.environ.pop("OCR_REVIEW_MAX_TOOLS", None)
    rs = _reload_gateway()

    argv = rs.build_ocr_review_argv("/usr/bin/ocr", "/work/repo", _sample_request())
    assert argv[:3] == ["/usr/bin/ocr", "review", "--repo"]
    assert "--concurrency" in argv
    assert "--exclude" not in argv
    assert "--max-tools" not in argv


def test_build_ocr_review_argv_with_exclude_and_max_tools(monkeypatch):
    monkeypatch.setenv("OCR_REVIEW_EXCLUDE", "**/*.xml,**/test/**")
    monkeypatch.setenv("OCR_REVIEW_MAX_TOOLS", "12")
    rs = _reload_gateway()
    monkeypatch.setattr(rs.gw_config, "ocr_review_supports_flag", lambda flag: True)

    argv = rs.build_ocr_review_argv("ocr", "/work/repo", _sample_request())
    idx = argv.index("--exclude")
    assert argv[idx + 1] == "**/*.xml,**/test/**"
    idx = argv.index("--max-tools")
    assert argv[idx + 1] == "12"


def test_build_ocr_review_argv_skips_unsupported_flags(monkeypatch):
    monkeypatch.setenv("OCR_REVIEW_EXCLUDE", "**/*.xml")
    monkeypatch.setenv("OCR_REVIEW_MAX_TOOLS", "12")
    rs = _reload_gateway()
    monkeypatch.setattr(rs.gw_config, "ocr_review_supports_flag", lambda flag: False)

    argv = rs.build_ocr_review_argv("ocr", "/work/repo", _sample_request())
    assert "--exclude" not in argv
    assert "--max-tools" not in argv

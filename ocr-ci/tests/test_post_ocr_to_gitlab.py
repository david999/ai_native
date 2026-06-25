from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from gitlab_mr import failure_note_body, ocr_result_path, ocr_stderr_path, post_review_from_files


def test_failure_note_body_with_stderr():
    body = failure_note_body("JSONDecodeError", "LLM 401 unauthorized")
    assert "OpenCodeReview" in body
    assert "401 unauthorized" in body


def test_failure_note_body_without_stderr():
    body = failure_note_body("[Errno 2] No such file", "")
    assert "could not read review output" in body
    assert "ocr review" in body


def test_ocr_paths_default():
    with patch.dict(os.environ, {}, clear=True):
        assert ocr_result_path() == "/tmp/ocr-result.json"
        assert ocr_stderr_path() == "/tmp/ocr-stderr.log"


def test_ocr_paths_from_env():
    with patch.dict(
        os.environ,
        {"OCR_RESULT_PATH": "/job/result.json", "OCR_STDERR_PATH": "/job/stderr.log"},
        clear=True,
    ):
        assert ocr_result_path() == "/job/result.json"
        assert ocr_stderr_path() == "/job/stderr.log"


def test_post_review_lenient_without_strict(tmp_path, monkeypatch):
    monkeypatch.delenv("OCR_POST_STRICT", raising=False)
    result_file = tmp_path / "r.json"
    result_file.write_text('{"comments": [], "message": "ok"}', encoding="utf-8")
    client = type("C", (), {"post_note": lambda self, body: {"success": False}})()
    assert post_review_from_files(client, result_path=str(result_file)) == 0

from __future__ import annotations

from post_ocr_to_gitlab import failure_note_body


def test_failure_note_body_with_stderr():
    body = failure_note_body("JSONDecodeError", "LLM 401 unauthorized")
    assert "OpenCodeReview" in body
    assert "401 unauthorized" in body


def test_failure_note_body_without_stderr():
    body = failure_note_body("[Errno 2] No such file", "")
    assert "could not read review output" in body
    assert "ocr review" in body

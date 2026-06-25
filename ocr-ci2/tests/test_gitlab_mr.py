"""gitlab_mr.py 单元测试（路径、strict 模式、client 辅助）。

覆盖：env 路径辅助函数、失败 note 正文、mock 的 post_review_from_files。
不测：真实 GitLab API。
"""
from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from gitlab_mr import (
    GitLabMrClient,
    failure_note_body,
    ocr_result_path,
    ocr_stderr_path,
    post_review_from_files,
)


def test_ocr_paths_default():
    with patch.dict(os.environ, {}, clear=True):
        assert ocr_result_path() == "/tmp/ocr-result.json"
        assert ocr_stderr_path() == "/tmp/ocr-stderr.log"


def test_ocr_paths_from_env():
    with patch.dict(
        os.environ,
        {"OCR_RESULT_PATH": "/data/r.json", "OCR_STDERR_PATH": "/data/e.log"},
        clear=True,
    ):
        assert ocr_result_path() == "/data/r.json"
        assert ocr_stderr_path() == "/data/e.log"


def test_failure_note_body_with_stderr():
    body = failure_note_body("JSONDecodeError", "LLM 401 unauthorized")
    assert "OpenCodeReview" in body
    assert "401 unauthorized" in body


def test_post_review_from_custom_path(tmp_path):
    result_file = tmp_path / "ocr-result.json"
    result_file.write_text(
        json.dumps({"comments": [], "message": "All clear."}),
        encoding="utf-8",
    )
    client = MagicMock(spec=GitLabMrClient)
    client.post_note.return_value = {"success": True}
    code = post_review_from_files(client, result_path=str(result_file))
    assert code == 0
    client.post_note.assert_called_once()
    assert "All clear" in client.post_note.call_args[0][0]


def test_post_review_strict_fails_when_no_api_success(tmp_path, monkeypatch):
    monkeypatch.setenv("OCR_POST_STRICT", "1")
    result_file = tmp_path / "ocr-result.json"
    result_file.write_text(json.dumps({"comments": [], "message": "ok"}), encoding="utf-8")
    client = MagicMock(spec=GitLabMrClient)
    client.post_note.return_value = {"success": False}
    code = post_review_from_files(client, result_path=str(result_file))
    assert code == 1


def test_post_review_lenient_when_api_fails(tmp_path, monkeypatch):
    monkeypatch.delenv("OCR_POST_STRICT", raising=False)
    result_file = tmp_path / "ocr-result.json"
    result_file.write_text(json.dumps({"comments": [], "message": "ok"}), encoding="utf-8")
    client = MagicMock(spec=GitLabMrClient)
    client.post_note.return_value = {"success": False}
    code = post_review_from_files(client, result_path=str(result_file))
    assert code == 0

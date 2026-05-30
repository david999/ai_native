#!/usr/bin/env python3
"""Local smoke tests for the LLM review engine (no Docker required)."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_parser():
    from app.review.parser import StructuredResponseParser, ParseError

    raw = json.dumps({
        "score": 45,
        "summary": "Found NPE risk",
        "issues": [{
            "file": "OrderService.java",
            "line": 64,
            "severity": "critical",
            "category": "null_safety",
            "message": "NPE risk",
            "suggestion": "Use orElseThrow",
        }],
    })
    result = StructuredResponseParser().parse(raw)
    assert result["score"] == 45.0
    assert len(result["issues"]) == 1

    bad_line = json.dumps({"score": 50, "summary": "x", "issues": [{"line": "bad", "file": "a.java"}]})
    result2 = StructuredResponseParser().parse(bad_line)
    assert result2["issues"][0]["line"] == 0

    try:
        StructuredResponseParser().parse("not json at all")
        assert False, "expected ParseError"
    except ParseError:
        pass
    print("OK parser")


def test_chunker_truncation():
    from app.review.chunker import DiffChunker

    huge = {"new_path": "Big.java", "old_path": "Big.java", "diff": "x" * 100000,
            "content": "y" * 100000, "is_supported": True}
    chunks = DiffChunker().chunk_files([huge])
    assert len(chunks) == 1
    assert "[truncated" in chunks[0]["files"][0]["diff"]
    print("OK chunker truncation")


def test_empty_chunks():
    from app.review.orchestrator import ReviewOrchestrator
    from app.exceptions import NoReviewableChangesError

    orch = ReviewOrchestrator(MagicMock(), MagicMock(), MagicMock())
    orch.context_builder.build = MagicMock(return_value=MagicMock(changed_files=[
        {"new_path": "README.md", "is_supported": False}
    ]))
    try:
        orch.run(1, 1)
        assert False, "expected NoReviewableChangesError"
    except NoReviewableChangesError:
        pass
    print("OK empty chunks")


def test_llm_failure_raises():
    from app.review.orchestrator import ReviewOrchestrator
    from app.exceptions import LLMReviewError

    llm = MagicMock()
    llm.chat.side_effect = RuntimeError("api down")

    ctx = MagicMock()
    ctx.changed_files = [{"new_path": "a.java", "old_path": "a.java", "diff": "+x",
                          "content": "", "is_supported": True}]
    ctx.context_md = ""
    ctx.title = ctx.description = ""

    orch = ReviewOrchestrator(MagicMock(), llm, MagicMock())
    orch.context_builder.build = MagicMock(return_value=ctx)

    try:
        orch.run(1, 1)
        assert False, "expected LLMReviewError"
    except LLMReviewError:
        pass
    print("OK llm failure")


def test_redact():
    from app.utils.redact import redact_secrets
    text = 'password=secret123\nglpat-abc.def.01'
    out = redact_secrets(text)
    assert "secret123" not in out
    assert "glpat-abc" not in out
    print("OK redact")


def test_health_import():
    from main import app
    assert app.title == "AICR Reviewer"
    print("OK app import")


def test_review_fail_open():
    from unittest.mock import patch
    from fastapi.testclient import TestClient
    from main import app
    from app.exceptions import LLMReviewError

    client = TestClient(app)
    with patch("app.api.routes._run_orchestrator", side_effect=LLMReviewError("timeout")):
        resp = client.post("/review", json={"project_id": 1, "mr_iid": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == 100.0
    assert body["review_completed"] is False
    assert "fail-open" in body["summary"]
    print("OK review fail-open")


def test_review_auth_fail_open():
    from unittest.mock import patch
    from fastapi import HTTPException
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    with patch("app.api.routes._verify_review_auth", side_effect=HTTPException(401, "Unauthorized")):
        resp = client.post("/review", json={"project_id": 1, "mr_iid": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_completed"] is False
    print("OK auth fail-open")


if __name__ == "__main__":
    test_parser()
    test_chunker_truncation()
    test_empty_chunks()
    test_llm_failure_raises()
    test_redact()
    test_health_import()
    test_review_fail_open()
    test_review_auth_fail_open()
    print("All smoke tests passed.")

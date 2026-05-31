#!/usr/bin/env python3
"""Local smoke tests for the LLM review engine (no Docker required)."""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

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
    ctx.project_id = 1
    ctx.mr_iid = 1
    ctx.diff_refs = None

    orch = ReviewOrchestrator(MagicMock(), llm, MagicMock())
    orch.context_builder.build = MagicMock(return_value=ctx)

    try:
        orch.run(1, 1)
        assert False, "expected LLMReviewError"
    except LLMReviewError:
        pass
    print("OK llm failure")


def test_partial_chunk_incomplete():
    from app.review.orchestrator import ReviewOrchestrator

    llm = MagicMock()
    responses = [
        RuntimeError("chunk 1 failed"),
        json.dumps({"score": 95, "summary": "ok", "issues": []}),
    ]

    def chat_fn(*_a, **_kw):
        item = responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    llm.chat.side_effect = chat_fn

    ctx = MagicMock()
    ctx.changed_files = [
        {"new_path": "a.java", "old_path": "a.java", "diff": "+a", "content": "", "is_supported": True},
        {"new_path": "b.java", "old_path": "b.java", "diff": "+b", "content": "", "is_supported": True},
    ]
    ctx.context_md = ""
    ctx.title = ctx.description = ""
    ctx.project_id = 1
    ctx.mr_iid = 1
    ctx.diff_refs = None

    orch = ReviewOrchestrator(MagicMock(), llm, MagicMock())
    orch.context_builder.build = MagicMock(return_value=ctx)
    orch.chunker.chunk_files = MagicMock(return_value=[
        {"files": [ctx.changed_files[0]], "total_chars": 10},
        {"files": [ctx.changed_files[1]], "total_chars": 10},
    ])

    with patch("app.review.orchestrator.REVIEW_DRY_RUN", True):
        result = orch.run(1, 1)

    assert result["review_completed"] is False
    assert result["score"] == 95.0
    assert "Partial LLM failures" in result["summary"]
    print("OK partial chunk incomplete")


def test_redact():
    from app.utils.redact import redact_secrets
    text = 'password=secret123\nglpat-abc.def.01'
    out = redact_secrets(text)
    assert "secret123" not in out
    assert "glpat-abc" not in out
    print("OK redact")


def test_redact_mr_metadata():
    from app.gitlab.context_builder import ContextBuilder
    from unittest.mock import MagicMock

    builder = ContextBuilder()
    mr = MagicMock()
    mr.title = "fix: password=leak123"
    mr.description = "token glpat-xxxx.yyyy.zzzz"
    mr.source_branch = "main"
    mr.target_branch = "dev"
    mr.diff_refs = {}
    mr.changes.return_value = {"changes": []}

    project = MagicMock()
    project.files.raw.side_effect = Exception("no context file")

    session = MagicMock()
    session.project = project
    session.mr = mr

    ctx = builder.build(1, 1, extra_diff="api_key=abc123secret", session=session)
    assert "leak123" in ctx.title
    assert "glpat-xxxx" not in ctx.description
    assert "abc123secret" not in ctx.changed_files[0]["diff"]
    print("OK redact mr metadata")


def test_health_import():
    from main import app
    assert app.title == "AICR Reviewer"
    print("OK app import")


def test_health_minimal():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body == {"status": "ok"}
    print("OK health minimal")


def test_review_fail_open():
    from fastapi.testclient import TestClient
    from main import app
    from app.exceptions import LLMReviewError

    client = TestClient(app)
    with patch("app.api.routes.REVIEW_API_SECRET", ""), \
         patch("app.api.routes.REVIEW_API_ALLOW_INSECURE", True), \
         patch("app.api.routes._run_orchestrator", side_effect=LLMReviewError("timeout")):
        resp = client.post("/review", json={"project_id": 1, "mr_iid": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["score"] == 100.0
    assert body["review_completed"] is False
    assert "fail-open" in body["summary"]
    print("OK review fail-open")


def test_review_auth_returns_401():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    with patch("app.api.routes.REVIEW_API_SECRET", "test-secret"), \
         patch("app.api.routes.REVIEW_API_ALLOW_INSECURE", False):
        resp = client.post("/review", json={"project_id": 1, "mr_iid": 1})
    assert resp.status_code == 401
    print("OK auth returns 401")


def test_review_secret_not_configured():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    with patch("app.api.routes.REVIEW_API_SECRET", ""), \
         patch("app.api.routes.REVIEW_API_ALLOW_INSECURE", False):
        resp = client.post("/review", json={"project_id": 1, "mr_iid": 1})
    assert resp.status_code == 503
    print("OK secret not configured 503")


if __name__ == "__main__":
    test_parser()
    test_chunker_truncation()
    test_empty_chunks()
    test_llm_failure_raises()
    test_partial_chunk_incomplete()
    test_redact()
    test_redact_mr_metadata()
    test_health_import()
    test_health_minimal()
    test_review_fail_open()
    test_review_auth_returns_401()
    test_review_secret_not_configured()
    print("All smoke tests passed.")

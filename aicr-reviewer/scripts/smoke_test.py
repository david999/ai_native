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


def test_parser_markdown_fence():
    from app.review.parser import StructuredResponseParser

    raw = """```json
{"score": 80, "summary": "ok", "issues": []}
```"""
    result = StructuredResponseParser().parse(raw)
    assert result["score"] == 80.0
    print("OK parser markdown fence")


def test_parser_score_clamp():
    from app.review.parser import StructuredResponseParser

    high = json.dumps({"score": 150, "summary": "x", "issues": []})
    low = json.dumps({"score": -10, "summary": "x", "issues": []})
    assert StructuredResponseParser().parse(high)["score"] == 100.0
    assert StructuredResponseParser().parse(low)["score"] == 0.0
    print("OK parser score clamp")


def test_parser_embedded_json():
    from app.review.parser import StructuredResponseParser

    raw = (
        "Here is the review:\n"
        '{"score": 72, "summary": "embedded", "issues": []}\n'
        "Thanks."
    )
    result = StructuredResponseParser().parse(raw)
    assert result["score"] == 72.0
    assert result["summary"] == "embedded"
    print("OK parser embedded json")


def test_parser_skips_non_dict_issues():
    from app.review.parser import StructuredResponseParser

    raw = json.dumps({
        "score": 90,
        "summary": "mixed issues",
        "issues": ["skip-me", {"file": "a.java", "line": 1, "message": "ok"}],
    })
    result = StructuredResponseParser().parse(raw)
    assert len(result["issues"]) == 1
    assert result["issues"][0]["file"] == "a.java"
    print("OK parser skips non-dict issues")


def test_chunker_truncation():
    from app.review.chunker import DiffChunker

    huge = {"new_path": "Big.java", "old_path": "Big.java", "diff": "x" * 100000,
            "content": "y" * 100000, "is_supported": True}
    chunks = DiffChunker().chunk_files([huge])
    assert len(chunks) == 1
    assert "[truncated" in chunks[0]["files"][0]["diff"]
    print("OK chunker truncation")


def test_chunker_splits_chunks():
    from app.review.chunker import DiffChunker

    files = [
        {
            "new_path": f"File{i}.java",
            "old_path": f"File{i}.java",
            "diff": "x" * 30000,
            "content": "",
            "is_supported": True,
        }
        for i in range(3)
    ]
    with patch("app.review.chunker.REVIEW_MAX_INPUT_TOKENS", 1000):
        chunks = DiffChunker().chunk_files(files)
    assert len(chunks) >= 2
    print("OK chunker splits chunks")


def test_diff_compress_deletion_only_hunk():
    from app.review.diff_compress import compress_unified_diff

    diff = (
        "@@ -1,3 +1,2 @@\n"
        " line\n"
        "-removed\n"
        "@@ -10,2 +10,3 @@\n"
        " ctx\n"
        "+added\n"
    )
    out = compress_unified_diff(diff)
    assert "-removed" not in out or "+added" in out
    assert "+added" in out
    print("OK diff compress deletion-only hunk")


def test_diff_compress_deletion_only_lines():
    from app.review.diff_compress import compress_changes

    changes = [{
        "old_path": "Auth.java",
        "new_path": "Auth.java",
        "diff": "@@ -1,3 +1,2 @@\n keep\n-removed_line\n",
        "deleted_file": False,
    }]
    files, deleted = compress_changes(changes)
    assert files == []
    assert deleted == ["Auth.java"]
    print("OK diff compress deletion-only lines")


def test_diff_compress_entire_file_delete():
    from app.review.diff_compress import compress_changes

    changes = [{
        "old_path": "gone.java",
        "new_path": "gone.java",
        "deleted_file": True,
        "diff": "@@ -1 +0,0 @@\n-old\n",
    }]
    files, deleted = compress_changes(changes)
    assert files == []
    assert deleted == ["gone.java"]
    print("OK diff compress entire file delete")


def test_language_priority_sort():
    from app.review.language_priority import sort_by_language_priority, infer_language_hint

    files = [
        {"new_path": "README.md", "old_path": "README.md"},
        {"new_path": "src/Main.java", "old_path": "src/Main.java"},
        {"new_path": "src/Util.java", "old_path": "src/Util.java"},
    ]
    ordered = sort_by_language_priority(files)
    assert ordered[0]["new_path"].endswith(".java")
    hint = infer_language_hint([
        {"new_path": "a.py", "old_path": "a.py"},
        {"new_path": "b.py", "old_path": "b.py"},
    ])
    assert hint == "Python"
    print("OK language priority")


def test_review_state_store():
    from pathlib import Path
    from app.review.review_state import ReviewStateStore

    base = Path(__file__).resolve().parents[1] / ".tmp-smoke-state"
    base.mkdir(exist_ok=True)
    store = ReviewStateStore(base_dir=base)
    store.set_last_reviewed_sha(9, 3, "abc123def")
    assert store.get_last_reviewed_sha(9, 3) == "abc123def"
    store.clear(9, 3)
    assert store.get_last_reviewed_sha(9, 3) is None
    print("OK review state store")


def test_token_utils_fallback():
    from app.review import token_utils

    token_utils.reset_encoder_cache()
    with patch("app.review.token_utils.REVIEW_USE_TIKTOKEN", False):
        n = token_utils.count_tokens("abcd" * 10)
        assert n == 10
    print("OK token utils fallback")


def test_chunker_skips_unsupported():
    from app.review.chunker import DiffChunker

    files = [
        {"new_path": "a.java", "old_path": "a.java", "diff": "+a", "is_supported": True},
        {"new_path": "README.md", "old_path": "README.md", "diff": "+b", "is_supported": False},
    ]
    chunks = DiffChunker().chunk_files(files)
    assert len(chunks) == 1
    assert len(chunks[0]["files"]) == 1
    assert chunks[0]["files"][0]["new_path"] == "a.java"
    print("OK chunker skips unsupported")


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


def test_orchestrator_deletions_only():
    from app.review.orchestrator import ReviewOrchestrator

    llm = MagicMock()
    llm.chat.return_value = json.dumps({
        "score": 85,
        "summary": "deletion ok",
        "issues": [],
    })

    ctx = MagicMock()
    ctx.changed_files = []
    ctx.deleted_files = ["Removed.java"]
    ctx.context_md = ""
    ctx.title = "remove file"
    ctx.description = ""
    ctx.project_id = 1
    ctx.mr_iid = 5
    ctx.diff_refs = None
    ctx.head_sha = "abc123"
    ctx.incremental_from_sha = None

    store = MagicMock()
    orch = ReviewOrchestrator(MagicMock(), llm, MagicMock(), state_store=store)
    orch.context_builder.build = MagicMock(return_value=ctx)

    with patch("app.review.orchestrator.REVIEW_DRY_RUN", False):
        orch.publisher.publish_summary = MagicMock(return_value=True)
        result = orch.run(1, 5)

    assert result["review_completed"] is True
    assert result["score"] == 85.0
    llm.chat.assert_called_once()
    store.set_last_reviewed_sha.assert_called_once_with(1, 5, "abc123")
    print("OK orchestrator deletions only")


def test_mr_review_lock():
    import threading
    from app.api.concurrency import (
        acquire_mr_review,
        release_mr_review,
        MRReviewBusyError,
        reset_mr_locks_for_tests,
    )

    reset_mr_locks_for_tests()
    acquire_mr_review(1, 99, timeout=1.0)
    errors = []

    def second():
        try:
            acquire_mr_review(1, 99, blocking=True, timeout=0.2)
            errors.append("should not acquire")
        except MRReviewBusyError:
            pass

    t = threading.Thread(target=second)
    t.start()
    t.join()
    release_mr_review(1, 99)
    reset_mr_locks_for_tests()
    assert errors == []
    print("OK mr review lock")


def test_review_mr_busy_409():
    from fastapi.testclient import TestClient
    from main import app
    from app.api.concurrency import MRReviewBusyError

    client = TestClient(app)
    with patch("app.api.routes.REVIEW_API_SECRET", ""), \
         patch("app.api.routes.REVIEW_API_ALLOW_INSECURE", True), \
         patch("app.api.routes.acquire_review_slot"), \
         patch("app.api.routes.release_review_slot"), \
         patch("app.api.routes.acquire_mr_review", side_effect=MRReviewBusyError("busy")):
        resp = client.post("/review", json={"project_id": 1, "mr_iid": 1})
    assert resp.status_code == 409
    print("OK review mr busy 409")


def test_orchestrator_success():
    from app.review.orchestrator import ReviewOrchestrator

    llm = MagicMock()
    llm.chat.return_value = json.dumps({
        "score": 88,
        "summary": "looks good",
        "issues": [{
            "file": "Svc.java",
            "line": 10,
            "severity": "warning",
            "category": "style",
            "message": "rename",
            "suggestion": "use verb",
        }],
    })

    ctx = MagicMock()
    ctx.changed_files = [{
        "new_path": "Svc.java",
        "old_path": "Svc.java",
        "diff": "+code",
        "content": "",
        "is_supported": True,
    }]
    ctx.context_md = ""
    ctx.title = "feat"
    ctx.description = ""
    ctx.project_id = 1
    ctx.mr_iid = 2
    ctx.diff_refs = None

    orch = ReviewOrchestrator(MagicMock(), llm, MagicMock())
    orch.context_builder.build = MagicMock(return_value=ctx)

    with patch("app.review.orchestrator.REVIEW_DRY_RUN", True):
        result = orch.run(1, 2)

    assert result["review_completed"] is True
    assert result["score"] == 88.0
    assert len(result["issues"]) == 1
    assert result["code_quality"][0]["check_name"] == "aicr-review"
    print("OK orchestrator success")


def test_redact():
    from app.utils.redact import redact_secrets
    text = 'password=secret123\nglpat-abc.def.01'
    out = redact_secrets(text)
    assert "secret123" not in out
    assert "glpat-abc" not in out
    print("OK redact")


def test_redact_aws_key():
    from app.utils.redact import redact_secrets

    text = "key=AKIAIOSFODNN7EXAMPLE"
    out = redact_secrets(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in out
    assert "AKIA***REDACTED***" in out
    print("OK redact aws key")


def test_supported_extensions():
    from app.gitlab.context_builder import _is_supported_path

    assert _is_supported_path("src/Main.java", "")
    assert _is_supported_path("", "Dockerfile")
    assert _is_supported_path("README.md", "README.md") is False
    assert _is_supported_path("pkg/main.kt", "") is True
    print("OK supported extensions")


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
    assert "leak123" not in ctx.title
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


def test_health_detail():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    resp = client.get("/health/detail")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "gitlab_url" in body
    assert "review_max_concurrent" in body
    print("OK health detail")


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


def test_review_no_reviewable_changes():
    from fastapi.testclient import TestClient
    from main import app
    from app.exceptions import NoReviewableChangesError

    client = TestClient(app)
    with patch("app.api.routes.REVIEW_API_SECRET", ""), \
         patch("app.api.routes.REVIEW_API_ALLOW_INSECURE", True), \
         patch("app.api.routes._run_orchestrator",
               side_effect=NoReviewableChangesError("only markdown")):
        resp = client.post("/review", json={"project_id": 1, "mr_iid": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert body["review_completed"] is False
    assert body["score"] == 100.0
    assert "only markdown" in body["summary"]
    print("OK review no reviewable changes")


def test_review_auth_returns_401():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    with patch("app.api.routes.REVIEW_API_SECRET", "test-secret"), \
         patch("app.api.routes.REVIEW_API_ALLOW_INSECURE", False):
        resp = client.post("/review", json={"project_id": 1, "mr_iid": 1})
    assert resp.status_code == 401
    print("OK auth returns 401")


def test_review_bearer_auth_ok():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    with patch("app.api.routes.REVIEW_API_SECRET", "bearer-secret"), \
         patch("app.api.routes.REVIEW_API_ALLOW_INSECURE", False), \
         patch("app.api.routes._run_orchestrator", return_value={
             "score": 75.0,
             "issues": [],
             "summary": "done",
             "review_completed": True,
             "code_quality": [],
         }):
        resp = client.post(
            "/review",
            json={"project_id": 1, "mr_iid": 1},
            headers={"Authorization": "Bearer bearer-secret"},
        )
    assert resp.status_code == 200
    assert resp.json()["review_completed"] is True
    assert resp.json()["score"] == 75.0
    print("OK bearer auth ok")


def test_review_secret_not_configured():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    with patch("app.api.routes.REVIEW_API_SECRET", ""), \
         patch("app.api.routes.REVIEW_API_ALLOW_INSECURE", False):
        resp = client.post("/review", json={"project_id": 1, "mr_iid": 1})
    assert resp.status_code == 503
    print("OK secret not configured 503")


def test_review_concurrency_503():
    from fastapi.testclient import TestClient
    from main import app
    from app.api.concurrency import ReviewCapacityError

    client = TestClient(app)
    with patch("app.api.routes.REVIEW_API_SECRET", ""), \
         patch("app.api.routes.REVIEW_API_ALLOW_INSECURE", True), \
         patch("app.api.routes.acquire_review_slot",
               side_effect=ReviewCapacityError("max=2")):
        resp = client.post("/review", json={"project_id": 1, "mr_iid": 1})
    assert resp.status_code == 503
    print("OK review concurrency 503")


def test_webhook_ignored():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    with patch("app.api.routes.GITLAB_WEBHOOK_SECRET", ""), \
         patch("app.api.routes.GITLAB_WEBHOOK_ALLOW_INSECURE", True):
        resp = client.post(
            "/webhook/gitlab",
            json={"object_kind": "push", "project": {"id": 1}},
        )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
    print("OK webhook ignored")


def test_webhook_unauthorized():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    with patch("app.api.routes.GITLAB_WEBHOOK_SECRET", "hook-secret"), \
         patch("app.api.routes.GITLAB_WEBHOOK_ALLOW_INSECURE", False):
        resp = client.post(
            "/webhook/gitlab",
            json={"object_kind": "merge_request"},
            headers={"X-Gitlab-Token": "wrong"},
        )
    assert resp.status_code == 401
    print("OK webhook unauthorized")


def test_webhook_accepted():
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    payload = {
        "object_kind": "merge_request",
        "object_attributes": {"action": "open", "iid": 9},
        "project": {"id": 42},
    }
    with patch("app.api.routes.GITLAB_WEBHOOK_SECRET", "hook-secret"), \
         patch("app.api.routes.GITLAB_WEBHOOK_ALLOW_INSECURE", False):
        resp = client.post(
            "/webhook/gitlab",
            json=payload,
            headers={"X-Gitlab-Token": "hook-secret"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "accepted"
    assert body["project_id"] == 42
    assert body["mr_iid"] == 9
    print("OK webhook accepted")


def test_llm_factory_missing_key():
    from app.llm.factory import create_llm_provider

    with patch("app.llm.factory.LLM_API_KEY", ""):
        try:
            create_llm_provider()
            assert False, "expected ValueError"
        except ValueError as e:
            assert "LLM_API_KEY" in str(e)
    print("OK llm factory missing key")


if __name__ == "__main__":
    tests = [
        test_parser,
        test_parser_markdown_fence,
        test_parser_score_clamp,
        test_parser_embedded_json,
        test_parser_skips_non_dict_issues,
        test_diff_compress_deletion_only_hunk,
        test_diff_compress_deletion_only_lines,
        test_diff_compress_entire_file_delete,
        test_language_priority_sort,
        test_review_state_store,
        test_token_utils_fallback,
        test_chunker_truncation,
        test_chunker_splits_chunks,
        test_chunker_skips_unsupported,
        test_empty_chunks,
        test_llm_failure_raises,
        test_partial_chunk_incomplete,
        test_orchestrator_deletions_only,
        test_mr_review_lock,
        test_review_mr_busy_409,
        test_orchestrator_success,
        test_redact,
        test_redact_aws_key,
        test_supported_extensions,
        test_redact_mr_metadata,
        test_health_import,
        test_health_minimal,
        test_health_detail,
        test_review_fail_open,
        test_review_no_reviewable_changes,
        test_review_auth_returns_401,
        test_review_bearer_auth_ok,
        test_review_secret_not_configured,
        test_review_concurrency_503,
        test_webhook_ignored,
        test_webhook_unauthorized,
        test_webhook_accepted,
        test_llm_factory_missing_key,
    ]
    for fn in tests:
        fn()
    print(f"All {len(tests)} smoke tests passed.")

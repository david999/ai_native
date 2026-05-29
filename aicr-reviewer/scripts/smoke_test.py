#!/usr/bin/env python3
"""Local smoke tests for the LLM review engine (no Docker required)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def test_parser():
    from app.review.parser import StructuredResponseParser

    raw = json.dumps({
        "score": 45,
        "summary": "Found NPE risk",
        "issues": [{
            "file": "order-service/src/main/java/com/example/order/service/OrderService.java",
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
    print("OK parser")


def test_chunker():
    from app.review.chunker import DiffChunker

    files = [
        {"new_path": "a.java", "old_path": "a.java", "diff": "+line", "content": "class A {}", "is_supported": True},
        {"new_path": "b.java", "old_path": "b.java", "diff": "+line", "content": "class B {}", "is_supported": True},
    ]
    chunks = DiffChunker().chunk_files(files)
    assert len(chunks) >= 1
    print("OK chunker")


def test_prompt_renderer():
    from app.review.prompt_renderer import PromptRenderer

    r = PromptRenderer()
    system = r.render_system(context_md="# Test context")
    user = r.render_user(mr_title="feat: demo", changed_files_summary="- a.java", diff_text="+ code")
    assert "Test context" in system
    assert "feat: demo" in user
    print("OK prompt_renderer")


def test_health_import():
    from main import app
    assert app.title == "AICR Reviewer"
    print("OK app import")


if __name__ == "__main__":
    test_parser()
    test_chunker()
    test_prompt_renderer()
    test_health_import()
    print("All smoke tests passed.")

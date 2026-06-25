"""Tests for OCR session JSONL parsing and publish regex assertions."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from assert_ocr_publish import collect_ocr_content, inline_note_is_review, note_is_ocr, parse_gitlab_ts
from assert_ocr_session import assert_ocr_session
from lib.ocr_session import find_session_jsonl, parse_session_jsonl
from lib.scenario_manifest import load_index, load_scenario_ids
from poll_gateway_job import parse_gateway_job_id
from wait_for_review import find_latest_review_job

FIXTURE_JSONL = Path(__file__).parent / "fixtures" / "minimal_session.jsonl"


def test_load_scenario_ids_all():
    ids = load_scenario_ids(True, None)
    assert len(ids) == 6
    assert "D01_feature_date_guard" in ids
    assert "D05_rule_severity_prefix" in ids
    assert "D06_rule_ai_standards" in ids


def test_load_scenario_ids_single():
    ids = load_scenario_ids(False, "D02_bug_npe_optional")
    assert ids == ["D02_bug_npe_optional"]


def test_manifest_has_assert_fields():
    for spec in load_index():
        assert spec.get("min_ocr_notes", 0) >= 1
        assert "branch" in spec


def test_d05_has_session_and_publish_assertions():
    spec = next(s for s in load_index() if s["id"] == "D05_rule_severity_prefix")
    assert spec["session"]["must_rule_r2_injected"] is True
    assert spec["session"]["severity_warnings_only"] is True
    assert spec["publish"]["regex_warnings_only"] is True


def test_d06_has_r1_session_assertions():
    spec = next(s for s in load_index() if s["id"] == "D06_rule_ai_standards")
    assert spec["session"]["must_rule_injected_or_read_agents"] is True
    assert spec["publish"]["keyword_warnings_only"] is True
    assert "must_match_regex" not in spec.get("publish", {})


def test_parse_gateway_job_id_from_trace():
    log = 'echo "Gateway job_id=abc-123-def (async)"'
    assert parse_gateway_job_id(log) == "abc-123-def"


def test_parse_gateway_job_id_from_json():
    log = '{"job_id":"job-xyz-99","status":"queued"}'
    assert parse_gateway_job_id(log) == "job-xyz-99"


def test_note_is_ocr_marker():
    assert note_is_ocr("✅ **OpenCodeReview**: Looks good")
    assert not note_is_ocr("random comment")


def test_collect_ocr_content_inline():
    notes = [{"body": "🔍 **OpenCodeReview** found **2** issue(s)", "created_at": "2026-06-25T12:00:00.000Z"}]
    discussions = [
        {
            "notes": [
                {
                    "type": "DiffNote",
                    "body": "Potential null dereference",
                    "position": {"new_line": 10},
                    "created_at": "2026-06-25T12:01:00.000Z",
                    "system": False,
                }
            ]
        }
    ]
    data = collect_ocr_content(notes, discussions)
    assert data["ocr_note_count"] == 1
    assert data["inline_count"] == 1


def test_collect_ocr_content_skips_system_inline():
    discussions = [
        {
            "notes": [
                {
                    "type": "DiffNote",
                    "body": "changed the description",
                    "position": {"new_line": 1},
                    "created_at": "2026-06-25T12:01:00.000Z",
                    "system": True,
                }
            ]
        }
    ]
    data = collect_ocr_content([], discussions)
    assert data["inline_count"] == 0


def test_inline_note_is_review_suggestion():
    assert inline_note_is_review({"body": "fix\n```suggestion\nx\n```", "type": "DiffNote"})
    assert not inline_note_is_review({"body": "x", "type": "DiffNote", "system": True})


def test_collect_ocr_content_filters_by_since():
    since = datetime(2026, 6, 25, 12, 0, 0, tzinfo=timezone.utc)
    notes = [
        {"body": "🔍 **OpenCodeReview** old run", "created_at": "2026-06-24T12:00:00.000Z"},
        {"body": "🔍 **OpenCodeReview** new run", "created_at": "2026-06-25T12:05:00.000Z"},
    ]
    data = collect_ocr_content(notes, [], since=since)
    assert data["ocr_note_count"] == 1
    assert "new run" in data["sample_bodies"][0]


def test_severity_regex_on_raw_text():
    raw = "Summary\n[MEDIUM] fix null check\n"
    assert re.findall(r"\[(HIGH|MEDIUM|LOW)\]", raw)


def test_parse_session_jsonl_fixture():
    parsed = parse_session_jsonl(FIXTURE_JSONL)
    assert parsed["rule_r1_injected"] is True
    assert parsed["rule_r2_injected"] is True
    assert parsed["read_agents"] is True
    assert parsed["read_ai_rules"] is True
    assert parsed["severity_in_trace"] >= 1
    assert "file_read" in parsed["tool_names"]
    assert parsed["session_id"] == "sess-test-001"


def test_find_session_jsonl_by_job_suffix(tmp_path, monkeypatch):
    sessions = tmp_path / "sessions"
    repo = sessions / "E_demo-worktrees-3-abc123job001"
    repo.mkdir(parents=True)
    target = repo / "sess-test-001.jsonl"
    target.write_text(FIXTURE_JSONL.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setenv("OCR_SESSIONS_DIR", str(sessions))
    found = find_session_jsonl("abc123job001")
    assert found == target


def test_assert_ocr_publish_regex_warning_only():
    from assert_ocr_publish import collect_ocr_content
    import assert_ocr_publish as pub

    notes = [{"body": "🔍 **OpenCodeReview** summary", "created_at": "2026-06-25T12:00:00.000Z"}]
    collected = collect_ocr_content(notes, [])
    assert collected["all_text_raw"]

    orig = pub.get_scenario_spec
    try:
        pub.get_scenario_spec = lambda _sid: {
            "min_ocr_notes": 1,
            "publish": {
                "must_match_regex": [r"\[(HIGH|MEDIUM|LOW)\]"],
                "regex_warnings_only": True,
            },
        }
        # Patch gitlab calls
        pub.gitlab_token = lambda: "token"
        pub.get_mr_notes = lambda *a, **k: notes
        pub.get_mr_discussions = lambda *a, **k: []
        result = pub.assert_ocr_publish(1, 1, "fake")
        assert result["ok"] is True
        assert any("regex" in w.lower() for w in result.get("warnings") or [])
    finally:
        pub.get_scenario_spec = orig


def test_assert_ocr_session_skips_when_no_config():
    result = assert_ocr_session("any-job", "D01_feature_date_guard")
    assert result["ok"] is True
    assert result["skipped"] is True


def test_find_review_job_waits_when_commit_pipeline_missing():
    """commit_sha set but no matching pipeline → None (caller keeps waiting)."""
    pipelines = [
        {"id": 99, "sha": "oldsha111"},
        {"id": 98, "sha": "oldsha222"},
    ]

    def fake_pipelines(token, project_id, mr_iid):
        return pipelines

    def fake_jobs(token, project_id, pipeline_id):
        return [{"name": "code-review", "id": 1, "status": "success"}]

    import wait_for_review as wr

    old_p = wr.get_mr_pipelines
    old_j = wr.get_pipeline_jobs
    try:
        wr.get_mr_pipelines = fake_pipelines
        wr.get_pipeline_jobs = fake_jobs
        assert find_latest_review_job("t", 1, 1, commit_sha="newsha000") is None
    finally:
        wr.get_mr_pipelines = old_p
        wr.get_pipeline_jobs = old_j

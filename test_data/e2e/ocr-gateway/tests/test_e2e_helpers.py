from __future__ import annotations

from datetime import datetime, timezone

from assert_ocr_publish import collect_ocr_content, inline_note_is_review, note_is_ocr, parse_gitlab_ts
from lib.scenario_manifest import load_index, load_scenario_ids
from poll_gateway_job import parse_gateway_job_id
from wait_for_review import find_latest_review_job


def test_load_scenario_ids_all():
    ids = load_scenario_ids(True, None)
    assert len(ids) == 4
    assert "D01_feature_date_guard" in ids
    assert "D04_bugfix_npe_guard" in ids


def test_load_scenario_ids_single():
    ids = load_scenario_ids(False, "D02_bug_npe_optional")
    assert ids == ["D02_bug_npe_optional"]


def test_manifest_has_assert_fields():
    for spec in load_index():
        assert spec.get("min_ocr_notes", 0) >= 1
        assert "branch" in spec


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

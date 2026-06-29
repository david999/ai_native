"""review_index.py 单元测试。"""

from __future__ import annotations

import json
import time

from review_index import (
    ReviewRecord,
    append_review_record,
    list_mr_latest_reviews,
    list_sessions_for_mr,
    load_all_records,
)


def test_append_and_load(tmp_path):
    index_path = tmp_path / "review-index.jsonl"
    record = ReviewRecord(
        job_id="abc123",
        project_id="111",
        project_path="group/proj",
        mr_iid="5",
        target_branch="master",
        commit_sha="deadbeef",
        status="success",
        comment_count=2,
        severity={"HIGH": 1, "MEDIUM": 0, "LOW": 1},
        tokens={"prompt": 100, "completion": 10, "total": 110, "llm_requests": 3},
    )
    append_review_record(record, path=index_path)
    loaded = load_all_records(path=index_path)
    assert len(loaded) == 1
    assert loaded[0].job_id == "abc123"
    assert loaded[0].comment_count == 2


def test_latest_per_mr(tmp_path):
    index_path = tmp_path / "review-index.jsonl"
    base = dict(
        project_id="111",
        project_path="group/proj",
        mr_iid="7",
        target_branch="main",
        commit_sha="aaa",
        status="success",
    )
    older = ReviewRecord(job_id="old", finished_at=time.time() - 100, **base)
    newer = ReviewRecord(job_id="new", finished_at=time.time(), **base)
    append_review_record(older, path=index_path)
    append_review_record(newer, path=index_path)

    latest = list_mr_latest_reviews(path=index_path)
    assert len(latest) == 1
    assert latest[0].job_id == "new"


def test_list_sessions_for_mr(tmp_path):
    index_path = tmp_path / "review-index.jsonl"
    for job_id in ("a", "b"):
        append_review_record(
            ReviewRecord(
                job_id=job_id,
                project_id="99",
                project_path="g/p",
                mr_iid="3",
                status="success",
                finished_at=time.time(),
            ),
            path=index_path,
        )
    history = list_sessions_for_mr("99", "3", path=index_path)
    assert len(history) == 2
    assert history[0].job_id in ("a", "b")


def test_failed_record(tmp_path):
    index_path = tmp_path / "review-index.jsonl"
    append_review_record(
        ReviewRecord(
            job_id="fail1",
            project_id="1",
            project_path="g/p",
            mr_iid="1",
            status="failed",
            message="ocr review exit 1",
        ),
        path=index_path,
    )
    records = load_all_records(path=index_path)
    assert records[0].status == "failed"
    assert records[0].session_id == ""

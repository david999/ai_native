"""review_service 单元测试（入队、MR note、mock）。

覆盖：默认关闭进度 note、patch worker 后的入队副作用。
不测：子进程 ocr review、git clone。
"""
from __future__ import annotations

from unittest.mock import patch

from gateway.review_service import ReviewRequest, enqueue_review, queue_depth





def test_enqueue_no_mr_note_by_default(monkeypatch):

    monkeypatch.delenv("OCR_GATEWAY_MR_NOTES", raising=False)

    notified: list[str] = []



    with patch("gateway.review_service._notify_mr", side_effect=lambda r, b: notified.append(b)), patch(

        "gateway.review_service._worker"

    ):

        req = ReviewRequest(

            project_id="2",

            project_path="g/p",

            mr_iid="1",

            target_branch="main",

            commit_sha="abc",

        )

        job = enqueue_review("job-test-0", req)

        assert job.status == "queued"

        assert notified == []





def test_enqueue_posts_queued_note_when_enabled(monkeypatch):

    monkeypatch.setenv("OCR_GATEWAY_MR_NOTES", "1")

    notified: list[str] = []



    with patch("gateway.review_service._notify_mr", side_effect=lambda r, b: notified.append(b)), patch(

        "gateway.review_service._worker"

    ):

        before = queue_depth()

        req = ReviewRequest(

            project_id="2",

            project_path="g/p",

            mr_iid="1",

            target_branch="main",

            commit_sha="abc",

        )

        job = enqueue_review("job-test-1", req)

        assert job.status == "queued"

        assert queue_depth() == before + 1

        assert notified and "queued" in notified[0].lower()



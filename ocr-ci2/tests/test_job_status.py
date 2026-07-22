"""job_status 模块测试。"""

from viewer.job_status import JOB_STATUS_LABELS, enrich_status_fields, job_status_label


def test_job_status_label_known():
    assert job_status_label("success") == "已完成"
    assert job_status_label("failed") == "失败"
    assert job_status_label("running") == "进行中"


def test_enrich_status_fields():
    row = enrich_status_fields({"status": "failed"})
    assert row["status_label"] == "失败"
    assert "失败" in row["status_hint"]
    assert row["status"] == "failed"


def test_all_known_statuses_have_labels():
    for key in ("success", "failed", "running", "queued"):
        assert key in JOB_STATUS_LABELS

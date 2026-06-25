"""workspace_cache 单元测试。

覆盖：clone URL 构造、token 脱敏、mirror LRU 淘汰。
不测：真实 git 网络、大规模文件系统 mirror。
"""
from __future__ import annotations

import importlib

import pytest

from gateway.workspace_cache import (
    WorkspaceCache,
    build_clone_url,
    build_fetch_refspecs,
    sanitize_git_output,
)


def test_build_clone_url():
    url = build_clone_url(
        "http://gitlab:8000",
        "java_group/spring-cloud-demo",
        "glpat-secret/token",
    )
    assert url.startswith("http://oauth2:")
    assert "gitlab:8000" in url
    assert url.endswith("/java_group/spring-cloud-demo.git")


def test_lru_eviction_removes_oldest_mirror(tmp_path):
    cache = WorkspaceCache(tmp_path, max_mirrors=2)
    for pid, ts in (("1", 100.0), ("2", 200.0)):
        bare = tmp_path / "mirrors" / pid
        bare.mkdir(parents=True)
        (bare / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        cache._mirror_last_used[pid] = ts

    cache._evict_lru_if_needed(keep_project_id="3")
    assert not (tmp_path / "mirrors" / "1").exists()
    assert (tmp_path / "mirrors" / "2").exists()
    assert cache.mirror_count() == 1


def test_lru_skips_active_project(tmp_path):
    cache = WorkspaceCache(tmp_path, max_mirrors=1)
    for pid, ts in (("1", 100.0), ("2", 200.0)):
        bare = tmp_path / "mirrors" / pid
        bare.mkdir(parents=True)
        (bare / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
        cache._mirror_last_used[pid] = ts
    cache.register_active("1")

    cache._evict_lru_if_needed(keep_project_id="3")
    assert (tmp_path / "mirrors" / "1").exists()
    assert not (tmp_path / "mirrors" / "2").exists()
    cache.unregister_active("1")


def test_invalid_project_id_rejected(tmp_path):
    cache = WorkspaceCache(tmp_path)
    with pytest.raises(ValueError, match="project_id"):
        cache.prepare(
            project_id="../1",
            clone_url="http://example/repo.git",
            target_branch="main",
            commit_sha="abc",
            job_id="j1",
        )


def test_build_fetch_refspecs_includes_mr_head_and_sha():
    specs = build_fetch_refspecs(
        "master",
        "a30f3cbe9edeb29be35b8302fdd2b0a4edc2ca3e",
        mr_iid="1",
    )
    assert specs[0] == "refs/heads/master:refs/remotes/origin/master"
    assert "refs/merge-requests/1/head" in specs[1]
    assert specs[2].startswith("a30f3cbe9edeb29be35b8302fdd2b0a4edc2ca3e:refs/ocr-fetch/")


def test_build_fetch_refspecs_skips_invalid_sha():
    specs = build_fetch_refspecs("main", "abc", mr_iid="2")
    assert len(specs) == 2
    assert "ocr-fetch" not in specs[1]


def test_job_artifact_paths_use_work_root(tmp_path, monkeypatch):
    import gateway.config as gw_cfg

    monkeypatch.setenv("OCR_GATEWAY_WORK_ROOT", str(tmp_path / "work"))
    monkeypatch.delenv("OCR_GATEWAY_TMP_DIR", raising=False)
    gw_cfg = importlib.reload(gw_cfg)
    result, stderr = gw_cfg.job_artifact_paths("job123")
    assert result.parent == stderr.parent
    assert str(result).replace("\\", "/").endswith("work/job-artifacts/ocr-result-job123.json")
    assert result.parent.is_dir()


def test_sanitize_git_output_redacts_token():
    raw = "fatal: https://oauth2:glpat-secret@gitlab:8000/foo.git not found"
    assert "glpat-secret" not in sanitize_git_output(raw)
    assert "oauth2:***@" in sanitize_git_output(raw)

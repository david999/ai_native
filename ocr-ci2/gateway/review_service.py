"""克隆 MR 仓库、执行 `ocr review`、将结果发帖到 GitLab。

逻辑清单：
- 队列：内存 job + threading.Semaphore(MAX_CONCURRENT) 工作池
- 流程：workspace 准备 → ocr review 子进程 → post_ocr_to_gitlab.py（OCR_POST_STRICT=1）
- MR note：仅 OCR_GATEWAY_MR_NOTES=1 时发进度 note；失败 note 始终发送
- 不做：跨重启持久化 job；ocr review 失败自动重试
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from gateway import config as gw_config
from gateway.workspace_cache import WorkspaceCache, build_clone_url, sanitize_git_output

_SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from gitlab_mr import GitLabMrClient
from ocr_ci_config import resolve_gitlab_api_token

logger = logging.getLogger(__name__)

_semaphore = threading.Semaphore(gw_config.MAX_CONCURRENT)
_workspace = WorkspaceCache(
    Path(gw_config.WORK_ROOT),
    max_mirrors=gw_config.WORKSPACE_MAX_MIRRORS,
)


@dataclass(frozen=True)
class ReviewRequest:
    project_id: str
    project_path: str
    mr_iid: str
    target_branch: str
    commit_sha: str


@dataclass
class ReviewJob:
    job_id: str
    status: str  # queued | running | success | failed
    message: str = ""
    finished_at: float | None = field(default=None)


_jobs: dict[str, ReviewJob] = {}
_jobs_lock = threading.Lock()


def get_job(job_id: str) -> ReviewJob | None:
    with _jobs_lock:
        return _jobs.get(job_id)


def _set_job(job_id: str, **kwargs: object) -> None:
    with _jobs_lock:
        job = _jobs[job_id]
        for key, value in kwargs.items():
            setattr(job, key, value)
        if job.status in ("success", "failed") and job.finished_at is None:
            job.finished_at = time.time()
    _prune_jobs()


def _prune_jobs() -> None:
    with _jobs_lock:
        if len(_jobs) <= gw_config.MAX_JOB_HISTORY:
            return
        completed = [
            (job_id, job)
            for job_id, job in _jobs.items()
            if job.status in ("success", "failed")
        ]
        completed.sort(key=lambda item: item[1].finished_at or 0.0)
        for job_id, _ in completed:
            if len(_jobs) <= gw_config.MAX_JOB_HISTORY:
                break
            del _jobs[job_id]


def queue_depth() -> int:
    with _jobs_lock:
        return sum(1 for j in _jobs.values() if j.status in ("queued", "running"))


def workspace_mirror_count() -> int:
    return _workspace.mirror_count()


def _mr_client(req: ReviewRequest) -> GitLabMrClient:
    return GitLabMrClient(
        gitlab_url=gw_config.GITLAB_API_URL,
        project_id=req.project_id,
        mr_iid=req.mr_iid,
        api_token=resolve_gitlab_api_token(),
        retry_base_delay=2.0,
        max_retries=3,
        success_delay=1.0,
        failure_delay=0.5,
        rate_limit_threshold=0,
    )


def _notify_mr(req: ReviewRequest, body: str) -> None:
    try:
        client = _mr_client(req)
        resp = client.post_note(body)
        if not resp.get("success"):
            logger.warning("failed to post MR note: %s", body[:80])
    except Exception as exc:
        logger.warning("MR note error: %s", exc)


def _notify_mr_progress(req: ReviewRequest, body: str) -> None:
    if gw_config.mr_progress_notes_enabled():
        _notify_mr(req, body)


def _git_error_message(exc: subprocess.CalledProcessError) -> str:
    detail = sanitize_git_output((exc.stderr or exc.stdout or str(exc))[-1500:])
    return f"git error: {detail}"


def _run_review_sync(job_id: str, req: ReviewRequest) -> None:
    token = resolve_gitlab_api_token()
    if not token:
        msg = "gitlab.api_token missing in gateway config"
        _set_job(job_id, status="failed", message=msg)
        _notify_mr(req, f"⚠️ **OpenCodeReview** (gateway): {msg}")
        return

    result_file, stderr_file = gw_config.job_artifact_paths(job_id)

    _workspace.register_active(req.project_id)
    try:
        _set_job(job_id, status="running", message="preparing repository")
        _notify_mr_progress(
            req,
            f"🕐 **OpenCodeReview** (gateway job `{job_id}`): preparing repository…",
        )
        clone_url = build_clone_url(gw_config.GITLAB_INTERNAL_URL, req.project_path, token)
        work_dir = _workspace.prepare(
            project_id=req.project_id,
            clone_url=clone_url,
            target_branch=req.target_branch,
            commit_sha=req.commit_sha,
            job_id=job_id,
            mr_iid=req.mr_iid,
        )

        _set_job(job_id, message="running ocr review")
        with result_file.open("w", encoding="utf-8") as out, stderr_file.open(
            "w", encoding="utf-8"
        ) as err:
            proc = subprocess.run(
                [
                    gw_config.resolve_executable("ocr"),
                    "review",
                    "--repo",
                    str(work_dir),
                    "--from",
                    f"origin/{req.target_branch}",
                    "--to",
                    req.commit_sha,
                    "--format",
                    "json",
                    "--audience",
                    "agent",
                    "--concurrency",
                    gw_config.OCR_CONCURRENCY,
                ],
                stdout=out,
                stderr=err,
                timeout=3600,
                **gw_config.SUBPROCESS_TEXT_KW,
            )
        if proc.returncode != 0:
            stderr_tail = sanitize_git_output(stderr_file.read_text(encoding="utf-8")[-2000:])
            msg = f"ocr review exit {proc.returncode}"
            _set_job(job_id, status="failed", message=f"{msg}: {stderr_tail[:500]}")
            _notify_mr(
                req,
                f"⚠️ **OpenCodeReview** (gateway job `{job_id}`): {msg}\n```\n{stderr_tail}\n```",
            )
            return

        _set_job(job_id, message="posting to GitLab MR")
        post_env = os.environ.copy()
        post_env.update(
            {
                "CI_SERVER_URL": gw_config.GITLAB_API_URL,
                "CI_PROJECT_ID": req.project_id,
                "CI_MERGE_REQUEST_IID": req.mr_iid,
                "CI_COMMIT_SHA": req.commit_sha,
                "OCR_RESULT_PATH": str(result_file),
                "OCR_STDERR_PATH": str(stderr_file),
                "OCR_POST_STRICT": "1",
            }
        )
        post_proc = subprocess.run(
            [sys.executable, gw_config.POST_SCRIPT],
            env=post_env,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if post_proc.returncode != 0:
            msg = f"post to GitLab failed: {post_proc.stderr[-800:]}"
            _set_job(job_id, status="failed", message=msg)
            _notify_mr(req, f"⚠️ **OpenCodeReview** (gateway job `{job_id}`): {msg}")
            return

        summary: dict = {}
        try:
            summary = json.loads(result_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
        comments = len(summary.get("comments") or [])
        _set_job(job_id, status="success", message=f"posted review ({comments} comment(s))")
        logger.info("job %s success comments=%s", job_id, comments)
    except subprocess.TimeoutExpired as exc:
        msg = f"timeout: {exc}"
        _set_job(job_id, status="failed", message=msg)
        _notify_mr(req, f"⚠️ **OpenCodeReview** (gateway job `{job_id}`): {msg}")
    except subprocess.CalledProcessError as exc:
        msg = _git_error_message(exc)
        _set_job(job_id, status="failed", message=msg)
        _notify_mr(req, f"⚠️ **OpenCodeReview** (gateway job `{job_id}`): {msg}")
    except ValueError as exc:
        msg = str(exc)
        _set_job(job_id, status="failed", message=msg)
        _notify_mr(req, f"⚠️ **OpenCodeReview** (gateway job `{job_id}`): {msg}")
    except FileNotFoundError as exc:
        msg = str(exc)
        _set_job(job_id, status="failed", message=msg)
        _notify_mr(req, f"⚠️ **OpenCodeReview** (gateway job `{job_id}`): {msg}")
    finally:
        _workspace.cleanup_worktree(req.project_id, job_id)
        _workspace.unregister_active(req.project_id)
        result_file.unlink(missing_ok=True)
        stderr_file.unlink(missing_ok=True)


def _worker(job_id: str, req: ReviewRequest) -> None:
    with _semaphore:
        _run_review_sync(job_id, req)


def enqueue_review(job_id: str, req: ReviewRequest) -> ReviewJob:
    """启动守护线程执行单次 MR 评审；立即返回 status=queued。

    不做：按 project_id+mr_iid 全局去重。
    """
    gw_config.validate_project_id(req.project_id)
    job = ReviewJob(job_id=job_id, status="queued")
    with _jobs_lock:
        _jobs[job_id] = job
    _notify_mr_progress(
        req,
        f"🕐 **OpenCodeReview** (gateway): review **queued** (job `{job_id}`). "
        "Comments will appear when processing completes.",
    )
    thread = threading.Thread(target=_worker, args=(job_id, req), daemon=True)
    thread.start()
    return job

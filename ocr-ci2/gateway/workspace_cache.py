"""按 GitLab 项目缓存 git 工作区（bare mirror + 每次评审独立 worktree）。

逻辑清单：
- prepare()：每 project_id 一个 bare mirror，每 job_id 一个临时 worktree
- LRU：WORKSPACE_MAX_MIRRORS>0 且非 active 时淘汰最久未用 mirror
- sanitize_git_output()：脱敏 git stderr 中的 oauth2 token
- 不做：跨 Gateway 进程共享 mirror；淘汰仍有 active job 的 mirror
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading
import time
import urllib.parse
from pathlib import Path

from gateway.config import SUBPROCESS_TEXT_KW, validate_project_id

logger = logging.getLogger(__name__)

_OAUTH_IN_URL = re.compile(r"oauth2:[^@\s/]+@", re.IGNORECASE)
_FULL_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def sanitize_git_output(text: str) -> str:
    """脱敏 git stderr 中可能出现的 OAuth token。"""
    return _OAUTH_IN_URL.sub("oauth2:***@", text)


def build_fetch_refspecs(
    target_branch: str,
    commit_sha: str,
    *,
    mr_iid: str | None = None,
) -> list[str]:
    """GitLab MR 评审所需 refspec；勿把 commit SHA 当作 remote ref 名直接 fetch。"""
    specs = [f"refs/heads/{target_branch}:refs/remotes/origin/{target_branch}"]
    if mr_iid:
        specs.append(
            f"refs/merge-requests/{mr_iid}/head:"
            f"refs/remotes/origin/merge-requests/{mr_iid}/head"
        )
    if _FULL_SHA_RE.fullmatch(commit_sha):
        specs.append(f"{commit_sha}:refs/ocr-fetch/{commit_sha}")
    return specs


class WorkspaceCache:
    """在 work_root 下复用 bare clone；每次评审一个独立 worktree。"""

    def __init__(self, work_root: Path, *, max_mirrors: int = 0) -> None:
        self.work_root = work_root.resolve()
        self.work_root.mkdir(parents=True, exist_ok=True)
        self.max_mirrors = max(0, max_mirrors)
        self._project_locks: dict[str, threading.Lock] = {}
        self._locks_guard = threading.Lock()
        self._mirror_last_used: dict[str, float] = {}
        self._active_jobs: dict[str, int] = {}
        self._active_guard = threading.Lock()

    def mirror_count(self) -> int:
        mirrors_dir = self.work_root / "mirrors"
        if not mirrors_dir.is_dir():
            return 0
        return sum(1 for path in mirrors_dir.iterdir() if (path / "HEAD").exists())

    def register_active(self, project_id: str) -> None:
        validate_project_id(project_id)
        with self._active_guard:
            self._active_jobs[project_id] = self._active_jobs.get(project_id, 0) + 1

    def unregister_active(self, project_id: str) -> None:
        with self._active_guard:
            count = self._active_jobs.get(project_id, 0) - 1
            if count <= 0:
                self._active_jobs.pop(project_id, None)
            else:
                self._active_jobs[project_id] = count

    def _is_active(self, project_id: str) -> bool:
        with self._active_guard:
            return self._active_jobs.get(project_id, 0) > 0

    def _mirror_path(self, project_id: str) -> Path:
        validate_project_id(project_id)
        path = (self.work_root / "mirrors" / project_id).resolve()
        if self.work_root not in path.parents:
            raise ValueError(f"unsafe mirror path for project_id={project_id!r}")
        return path

    def _worktree_path(self, project_id: str, job_id: str) -> Path:
        validate_project_id(project_id)
        if not job_id or "/" in job_id or "\\" in job_id or ".." in job_id:
            raise ValueError(f"invalid job_id: {job_id!r}")
        path = (self.work_root / "worktrees" / project_id / job_id).resolve()
        if self.work_root not in path.parents:
            raise ValueError(f"unsafe worktree path for job_id={job_id!r}")
        return path

    def _lock_for(self, project_id: str) -> threading.Lock:
        with self._locks_guard:
            if project_id not in self._project_locks:
                self._project_locks[project_id] = threading.Lock()
            return self._project_locks[project_id]

    def _touch_mirror(self, project_id: str) -> None:
        self._mirror_last_used[project_id] = time.time()

    def _list_mirror_ids(self) -> list[str]:
        mirrors_dir = self.work_root / "mirrors"
        if not mirrors_dir.is_dir():
            return []
        return sorted(
            path.name for path in mirrors_dir.iterdir() if path.is_dir() and (path / "HEAD").exists()
        )

    def _remove_mirror(self, project_id: str) -> None:
        if self._is_active(project_id):
            logger.info("workspace cache: skip evict active project_id=%s", project_id)
            return
        bare_dir = self._mirror_path(project_id)
        worktrees_root = self.work_root / "worktrees" / project_id
        if bare_dir.is_dir():
            shutil.rmtree(bare_dir, ignore_errors=True)
        if worktrees_root.is_dir():
            shutil.rmtree(worktrees_root, ignore_errors=True)
        self._mirror_last_used.pop(project_id, None)
        logger.info("workspace cache: evicted mirror project_id=%s", project_id)

    def _evict_lru_if_needed(self, *, keep_project_id: str) -> None:
        if self.max_mirrors <= 0:
            return
        mirror_ids = self._list_mirror_ids()
        if keep_project_id not in mirror_ids and len(mirror_ids) >= self.max_mirrors:
            mirror_ids.append(keep_project_id)
        while len(mirror_ids) > self.max_mirrors:
            candidates = [
                pid
                for pid in mirror_ids
                if pid != keep_project_id and not self._is_active(pid)
            ]
            if not candidates:
                break
            oldest = min(candidates, key=lambda pid: self._mirror_last_used.get(pid, 0.0))
            self._remove_mirror(oldest)
            mirror_ids.remove(oldest)

    def prepare(
        self,
        *,
        project_id: str,
        clone_url: str,
        target_branch: str,
        commit_sha: str,
        job_id: str,
        mr_iid: str | None = None,
    ) -> Path:
        """返回含完整 git 历史的目录，供 ocr review --from/--to 使用。"""
        bare_dir = self._mirror_path(project_id)
        worktree_dir = self._worktree_path(project_id, job_id)

        with self._lock_for(project_id):
            self._evict_lru_if_needed(keep_project_id=project_id)
            bare_dir.parent.mkdir(parents=True, exist_ok=True)
            if not (bare_dir / "HEAD").exists():
                logger.info("workspace cache: initial mirror clone project_id=%s", project_id)
                subprocess.run(
                    ["git", "clone", "--mirror", clone_url, str(bare_dir)],
                    check=True,
                    capture_output=True,
                    timeout=900,
                    **SUBPROCESS_TEXT_KW,
                )
            else:
                logger.info("workspace cache: fetch project_id=%s", project_id)
                subprocess.run(
                    ["git", "remote", "set-url", "origin", clone_url],
                    cwd=bare_dir,
                    check=True,
                    capture_output=True,
                    **SUBPROCESS_TEXT_KW,
                    timeout=30,
                )
                subprocess.run(
                    ["git", "fetch", "origin", "--prune"],
                    cwd=bare_dir,
                    check=True,
                    capture_output=True,
                    **SUBPROCESS_TEXT_KW,
                    timeout=600,
                )

            fetch_specs = build_fetch_refspecs(
                target_branch, commit_sha, mr_iid=mr_iid
            )
            subprocess.run(
                ["git", "fetch", "origin", *fetch_specs],
                cwd=bare_dir,
                check=True,
                capture_output=True,
                **SUBPROCESS_TEXT_KW,
                timeout=300,
            )
            self._touch_mirror(project_id)

            if worktree_dir.exists():
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree_dir)],
                    cwd=bare_dir,
                    capture_output=True,
                    **SUBPROCESS_TEXT_KW,
                    timeout=120,
                )
            worktree_dir.parent.mkdir(parents=True, exist_ok=True)
            subprocess.run(
                ["git", "worktree", "add", "--detach", str(worktree_dir), commit_sha],
                cwd=bare_dir,
                check=True,
                capture_output=True,
                **SUBPROCESS_TEXT_KW,
                timeout=120,
            )
            _verify_refs(worktree_dir, target_branch, commit_sha)

        return worktree_dir

    def cleanup_worktree(self, project_id: str, job_id: str) -> None:
        bare_dir = self._mirror_path(project_id)
        worktree_dir = self._worktree_path(project_id, job_id)
        if not worktree_dir.exists():
            return
        with self._lock_for(project_id):
            if not bare_dir.is_dir():
                logger.warning(
                    "workspace cache: mirror missing during cleanup project_id=%s", project_id
                )
                shutil.rmtree(worktree_dir, ignore_errors=True)
                return
            proc = subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree_dir)],
                cwd=bare_dir,
                capture_output=True,
                **SUBPROCESS_TEXT_KW,
                timeout=120,
            )
            if proc.returncode != 0:
                logger.warning(
                    "workspace cache: worktree remove failed project_id=%s job_id=%s: %s",
                    project_id,
                    job_id,
                    sanitize_git_output(proc.stderr or proc.stdout or ""),
                )


def _verify_refs(work_dir: Path, target_branch: str, commit_sha: str) -> None:
    for ref in (f"origin/{target_branch}", commit_sha):
        subprocess.run(
            ["git", "rev-parse", "--verify", ref],
            cwd=work_dir,
            check=True,
            capture_output=True,
            timeout=30,
            **SUBPROCESS_TEXT_KW,
        )


def build_clone_url(gitlab_internal_url: str, project_path: str, token: str) -> str:
    base = gitlab_internal_url.rstrip("/")
    parsed = urllib.parse.urlparse(base)
    host = parsed.netloc or parsed.path
    scheme = parsed.scheme or "http"
    safe_token = urllib.parse.quote(token, safe="")
    safe_path = project_path.strip("/")
    return f"{scheme}://oauth2:{safe_token}@{host}/{safe_path}.git"

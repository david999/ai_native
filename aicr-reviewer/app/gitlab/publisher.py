import logging
import hashlib
from typing import Optional

from app.gitlab.client import get_gitlab_client
from app.config import SCORE_THRESHOLD

logger = logging.getLogger("aicr")


def _make_fingerprint(file_path: str, line: int, category: str) -> str:
    return hashlib.md5(f"{file_path}:{line}:{category}".encode()).hexdigest()


class GitLabPublisher:
    def __init__(self):
        self._seen: set = set()

    def publish_issue(
        self,
        project_id: int,
        mr_iid: int,
        body: str,
        file_path: str,
        line: int,
        diff_refs: Optional[dict],
        category: str = "",
    ):
        fp = _make_fingerprint(file_path, line, category)
        if fp in self._seen:
            logger.debug(f"Duplicate comment skipped: {file_path}:{line} [{category}]")
            return
        self._seen.add(fp)

        gl = get_gitlab_client()
        project = gl.projects.get(project_id)
        mr = project.mergerequests.get(mr_iid)

        if file_path and diff_refs and line > 0:
            try:
                self._post_inline(mr, body, file_path, line, diff_refs)
                logger.info(f"Posted inline discussion on {file_path}:{line}")
                return
            except Exception as e:
                logger.warning(f"Inline discussion failed ({file_path}:{line}): {e}")

        try:
            self._post_note(mr, body, file_path, line)
            logger.info(f"Posted MR note fallback for {file_path}:{line}")
        except Exception as e:
            logger.error(f"MR note fallback also failed: {e}")

    def publish_summary(
        self,
        project_id: int,
        mr_iid: int,
        score: float,
        summary: str,
        issue_count: int,
        threshold: float = SCORE_THRESHOLD,
    ):
        gl = get_gitlab_client()
        project = gl.projects.get(project_id)
        mr = project.mergerequests.get(mr_iid)

        status = "PASSED" if score >= threshold else "FAILED"
        body = (
            f"## AICR Review Summary: {status}\n\n"
            f"- **Score**: {score}/100\n"
            f"- **Threshold**: {threshold}\n"
            f"- **Issues found**: {issue_count}\n\n"
            f"{summary}\n"
        )
        try:
            mr.notes.create({"body": body})
            logger.info(f"Posted summary note for MR !{mr_iid}")
        except Exception as e:
            logger.error(f"Failed to post summary: {e}")

    @staticmethod
    def _post_inline(mr, body: str, file_path: str, new_line: int, diff_refs: dict):
        position = {
            "base_sha": diff_refs["base_sha"],
            "start_sha": diff_refs["start_sha"],
            "head_sha": diff_refs["head_sha"],
            "position_type": "text",
            "new_path": file_path,
            "new_line": new_line,
        }
        mr.discussions.create({"body": body, "position": position})

    @staticmethod
    def _post_note(mr, body: str, file_path: str, line: int):
        note_body = (
            f"{body}\n\n"
            f"> 未能写入行内评论（该行可能不在 MR diff 中），位置参考："
            f"`{file_path}:{line}`"
        )
        mr.notes.create({"body": note_body})

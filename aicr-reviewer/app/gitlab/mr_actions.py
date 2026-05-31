"""GitLab MR 写操作：更新描述、发布 note、回复讨论。"""

from __future__ import annotations

import logging
from typing import Optional

from app.gitlab.session import GitLabMRSession, gitlab_call

logger = logging.getLogger("aicr")


class GitLabMRActions:
    def update_mr_description(
        self,
        project_id: int,
        mr_iid: int,
        *,
        description: str,
        title: Optional[str] = None,
        session: Optional[GitLabMRSession] = None,
    ) -> bool:
        gl_session = session or GitLabMRSession(project_id, mr_iid)
        mr = gl_session.mr
        attrs = {"description": description}
        if title:
            attrs["title"] = title
        try:
            gitlab_call(lambda: mr.save(**attrs))
            logger.info(f"Updated MR !{mr_iid} description")
            return True
        except Exception as e:
            logger.error(f"Failed to update MR !{mr_iid}: {e}")
            return False

    def post_note(
        self,
        project_id: int,
        mr_iid: int,
        body: str,
        *,
        session: Optional[GitLabMRSession] = None,
    ) -> bool:
        gl_session = session or GitLabMRSession(project_id, mr_iid)
        try:
            gitlab_call(lambda: gl_session.mr.notes.create({"body": body}))
            logger.info(f"Posted note on MR !{mr_iid}")
            return True
        except Exception as e:
            logger.error(f"Failed to post note on MR !{mr_iid}: {e}")
            return False

    def reply_to_note(
        self,
        project_id: int,
        mr_iid: int,
        discussion_id: str,
        body: str,
        *,
        session: Optional[GitLabMRSession] = None,
    ) -> bool:
        gl_session = session or GitLabMRSession(project_id, mr_iid)
        try:
            discussion = gitlab_call(
                lambda: gl_session.mr.discussions.get(discussion_id)
            )
            gitlab_call(lambda: discussion.notes.create({"body": body}))
            logger.info(f"Replied in discussion {discussion_id} on MR !{mr_iid}")
            return True
        except Exception as e:
            logger.warning(
                f"Discussion reply failed ({discussion_id}), falling back to note: {e}"
            )
            return self.post_note(project_id, mr_iid, body, session=gl_session)

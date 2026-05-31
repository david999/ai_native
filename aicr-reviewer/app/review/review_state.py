"""持久化 MR 上次评审通过的 head SHA，用于增量 compare。"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app.config import AICR_INCREMENTAL_REVIEW, AICR_STATE_DIR

logger = logging.getLogger("aicr")


class ReviewStateStore:
    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or AICR_STATE_DIR
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, project_id: int, mr_iid: int) -> Path:
        return self.base_dir / f"project_{project_id}_mr_{mr_iid}.json"

    def get_last_reviewed_sha(self, project_id: int, mr_iid: int) -> Optional[str]:
        if not AICR_INCREMENTAL_REVIEW:
            return None
        path = self._path(project_id, mr_iid)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sha = data.get("last_reviewed_sha")
            return str(sha) if sha else None
        except (OSError, json.JSONDecodeError) as e:
            logger.warning(f"Could not read review state {path}: {e}")
            return None

    def set_last_reviewed_sha(self, project_id: int, mr_iid: int, sha: str) -> None:
        if not AICR_INCREMENTAL_REVIEW or not sha:
            return
        payload = self._read_payload(project_id, mr_iid)
        payload["last_reviewed_sha"] = sha
        payload["updated_at"] = datetime.now(timezone.utc).isoformat()
        try:
            self._write_payload(project_id, mr_iid, payload)
        except OSError:
            raise
        logger.info(f"Saved review state for project={project_id} MR !{mr_iid} sha={sha[:8]}")

    def clear(self, project_id: int, mr_iid: int) -> None:
        path = self._path(project_id, mr_iid)
        if path.is_file():
            path.unlink(missing_ok=True)

    def _read_payload(self, project_id: int, mr_iid: int) -> dict:
        path = self._path(project_id, mr_iid)
        if not path.is_file():
            return {}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_payload(self, project_id: int, mr_iid: int, payload: dict) -> None:
        path = self._path(project_id, mr_iid)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def set_suppress_webhook_review(
        self,
        project_id: int,
        mr_iid: int,
        *,
        seconds: int = 120,
    ) -> None:
        """describe 写回 MR 后短暂跳过 MR update webhook 触发的全量评审。"""
        payload = self._read_payload(project_id, mr_iid)
        until = datetime.now(timezone.utc) + timedelta(seconds=max(1, seconds))
        payload["suppress_webhook_review_until"] = until.isoformat()
        self._write_payload(project_id, mr_iid, payload)
        logger.info(
            f"Suppress webhook review for project={project_id} MR !{mr_iid} "
            f"until {until.isoformat()}"
        )

    def is_webhook_review_suppressed(self, project_id: int, mr_iid: int) -> bool:
        payload = self._read_payload(project_id, mr_iid)
        raw = payload.get("suppress_webhook_review_until")
        if not raw:
            return False
        try:
            until = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
        except ValueError:
            return False
        if datetime.now(timezone.utc) >= until:
            return False
        return True

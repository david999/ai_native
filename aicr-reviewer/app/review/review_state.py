"""持久化 MR 上次评审通过的 head SHA，用于增量 compare。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
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
        path = self._path(project_id, mr_iid)
        payload = {
            "last_reviewed_sha": sha,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info(f"Saved review state for project={project_id} MR !{mr_iid} sha={sha[:8]}")

    def clear(self, project_id: int, mr_iid: int) -> None:
        path = self._path(project_id, mr_iid)
        if path.is_file():
            path.unlink(missing_ok=True)

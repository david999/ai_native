"""Locate OCR session JSONL for a Gateway review job_id."""

from __future__ import annotations

from pathlib import Path

from session_telemetry import SessionTelemetry, scan_session_jsonl, sessions_root


def repo_dir_matches_job(dir_name: str, gateway_job_id: str) -> bool:
    """Match OCR session repo slug ending with ``-{job_id}`` or exactly ``job_id``."""
    if not gateway_job_id:
        return False
    if dir_name == gateway_job_id:
        return True
    suffix = f"-{gateway_job_id}"
    return len(dir_name) > len(gateway_job_id) and dir_name.endswith(suffix)


def find_session_jsonl_path(job_id: str, root: Path | None = None) -> Path | None:
    """Locate newest JSONL file for a Gateway worktree *job_id*."""
    root = root or sessions_root()
    if not root.is_dir() or not job_id:
        return None

    candidates: list[Path] = []
    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        if repo_dir_matches_job(entry.name, job_id):
            candidates.extend(entry.glob("*.jsonl"))

    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def find_session_for_job(job_id: str, root: Path | None = None) -> SessionTelemetry | None:
    path = find_session_jsonl_path(job_id, root=root)
    if path is None:
        return None
    return scan_session_jsonl(path)

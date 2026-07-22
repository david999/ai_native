#!/usr/bin/env python3
"""根据本地 OCR Session 生成 Gateway MR 评审索引（review-index.jsonl）演示数据。

用途：
- 本地 Dashboard 无 MR 列表时，快速填充工作台 / 统计页测试数据
- 将已有 session JSONL 关联为多条 MR 记录（不同 mr_iid / job_id / 状态）

示例：
    cd ocr-ci2
    python scripts/seed_dashboard_demo.py
    python scripts/seed_dashboard_demo.py --clear --per-repo 3
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import time
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SCRIPTS = _ROOT / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

from review_index import ReviewRecord, append_review_record, load_all_records, review_index_path  # noqa: E402
from session_telemetry import discover_repos, list_repo_sessions, sessions_root  # noqa: E402


def _project_path_from_session(session) -> str:
    """从 session cwd 推断 GitLab project_path（尽量贴近真实路径）。"""
    cwd = (session.cwd or "").replace("\\", "/").strip("/")
    for marker in ("java_group/", "go_group/", "test_data/"):
        if marker in cwd:
            return cwd.split(marker, 1)[1]
    name = Path(cwd).name if cwd else session.repo_slug
    return f"demo_group/{name}"


def _stable_project_id(project_path: str) -> str:
    """同一 project_path 复用稳定 project_id。"""
    digest = hashlib.sha1(project_path.encode("utf-8")).hexdigest()[:8]
    return str(int(digest, 16) % 90000 + 10000)


def _build_demo_record(
    *,
    job_id: str,
    project_id: str,
    project_path: str,
    mr_iid: str,
    session,
    status: str,
    finished_at: float,
) -> ReviewRecord:
    """由 SessionTelemetry 构造一条 review-index 记录。"""
    sev = session.severity
    tokens = session.tokens
    high_preview = []
    for comment in session.high_comments[:3]:
        high_preview.append(
            {
                "file_path": comment.file_path,
                "line": comment.line,
                "snippet": comment.snippet,
            }
        )
    return ReviewRecord(
        job_id=job_id,
        project_id=project_id,
        project_path=project_path,
        mr_iid=mr_iid,
        target_branch="main",
        commit_sha=f"demo{job_id[-8:]:0>8}"[:16],
        status=status,
        message="seed demo" if status == "success" else "seed demo failed",
        finished_at=finished_at,
        session_id=session.session_id,
        encoded_repo=session.repo_slug,
        comment_count=len(session.all_comments),
        severity={"HIGH": sev.high, "MEDIUM": sev.medium, "LOW": sev.low},
        tokens={
            "prompt": tokens.prompt_tokens,
            "completion": tokens.completion_tokens,
            "total": tokens.total,
            "llm_requests": tokens.request_count,
        },
        high_preview=high_preview,
    )


def seed_demo_records(
    *,
    index_path: Path | None = None,
    sessions_root_path: Path | None = None,
    per_repo: int = 2,
    include_failed: bool = True,
    dry_run: bool = False,
) -> list[ReviewRecord]:
    """扫描本地 Session 并写入演示 MR 索引。"""
    root = sessions_root_path or sessions_root()
    index = index_path or review_index_path()
    created: list[ReviewRecord] = []
    now = time.time()

    repos = discover_repos(root)
    if not repos:
        print(f"[seed] 未在 {root} 发现 Session 仓库，跳过。")
        return created

    for repo_idx, repo in enumerate(repos):
        sessions = list_repo_sessions(root, repo.encoded_path)
        if not sessions:
            continue
        project_path = _project_path_from_session(sessions[0])
        project_id = _stable_project_id(project_path)

        # 每个 session 映射一条 MR；不足 per_repo 时用最新 session 复用不同 mr_iid
        pairs: list[tuple] = []
        for i, session in enumerate(sessions[:per_repo]):
            pairs.append((session, 100 + repo_idx * 10 + i))
        while len(pairs) < per_repo:
            pairs.append((sessions[0], 200 + repo_idx * 10 + len(pairs)))

        for offset, (session, mr_iid) in enumerate(pairs):
            status = "success"
            if include_failed and offset == len(pairs) - 1 and len(pairs) > 1:
                status = "failed"
            job_id = f"demo-{repo.encoded_path[:12]}-mr{mr_iid}"
            finished_at = now - (repo_idx * 3600 + offset * 600)
            record = _build_demo_record(
                job_id=job_id,
                project_id=project_id,
                project_path=project_path,
                mr_iid=str(mr_iid),
                session=session,
                status=status,
                finished_at=finished_at,
            )
            created.append(record)
            if dry_run:
                print(
                    f"[dry-run] {record.job_id} -> {record.project_path} !{record.mr_iid} "
                    f"({record.status}, H{record.severity.get('HIGH', 0)})"
                )
            else:
                append_review_record(record, index)

    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed review-index.jsonl from local OCR sessions")
    parser.add_argument(
        "--index-path",
        default="",
        help="review-index.jsonl 路径（默认 OCR_REVIEW_INDEX_PATH 或 work 目录）",
    )
    parser.add_argument(
        "--sessions-dir",
        default="",
        help="Session JSONL 根目录（默认 OCR_SESSIONS_DIR）",
    )
    parser.add_argument("--per-repo", type=int, default=2, help="每个仓库生成的 MR 条数")
    parser.add_argument("--clear", action="store_true", help="写入前清空索引文件")
    parser.add_argument("--no-failed", action="store_true", help="不生成 failed 状态记录")
    parser.add_argument("--dry-run", action="store_true", help="仅打印将写入的记录")
    args = parser.parse_args()

    index = Path(args.index_path) if args.index_path else review_index_path()
    sessions_dir = Path(args.sessions_dir) if args.sessions_dir else sessions_root()

    if args.clear and not args.dry_run:
        if index.is_file():
            index.unlink()
            print(f"[seed] 已清空 {index}")

    before = len(load_all_records(index))
    created = seed_demo_records(
        index_path=index,
        sessions_root_path=sessions_dir,
        per_repo=max(1, args.per_repo),
        include_failed=not args.no_failed,
        dry_run=args.dry_run,
    )
    after = len(load_all_records(index)) if not args.dry_run else before + len(created)

    print(
        f"[seed] 完成：新增 {len(created)} 条，索引 {before} -> {after} "
        f"({index if not args.dry_run else 'dry-run'})"
    )
    return 0 if created or before else 1


if __name__ == "__main__":
    raise SystemExit(main())

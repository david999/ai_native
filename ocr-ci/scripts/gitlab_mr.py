"""GitLab MR API 工具，供 post_ocr_to_gitlab.py 与 OCR Gateway 共用。

逻辑清单：
- GitLabMrClient：Note 与行内讨论，含重试与限流退避
- Token 顺序：显式参数 > GITLAB_API_TOKEN > config.json > CI_JOB_TOKEN（JOB-TOKEN 头）
- post_strict_enabled()：OCR_POST_STRICT=1 时解析失败则发帖失败（Gateway 会设置）
- 不做：发帖前校验 MR 是否存在；批量处理多个 MR
"""

from __future__ import annotations

import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from ocr_ci_config import resolve_gitlab_api_token

SEVERITY_COLOR_RE = re.compile(r"\[(HIGH|MEDIUM|LOW)\]")
# Plan B: GitLab CE 常剥离 inline style；用 emoji + <strong>（Markdown 粗体）
SEVERITY_MARKERS = {
    "HIGH": "🔴",
    "MEDIUM": "🟡",
    "LOW": "⚪",
}
_ALREADY_MARKED_RE = re.compile(r"[🔴🟡⚪]\s*\[(HIGH|MEDIUM|LOW)\]")


def severity_color_enabled() -> bool:
    """OCR_SEVERITY_COLOR=1（默认）时为 [HIGH]/[MEDIUM]/[LOW] 加 emoji + 粗体。"""
    val = os.environ.get("OCR_SEVERITY_COLOR", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def colorize_severity(text: str) -> str:
    if not text or not severity_color_enabled():
        return text

    def _replacer(match: re.Match[str]) -> str:
        level = match.group(1)
        start = match.start()
        window = text[max(0, start - 12) : start]
        if _ALREADY_MARKED_RE.search(window) or "<strong>" in window:
            return match.group(0)
        emoji = SEVERITY_MARKERS.get(level, "")
        prefix = f"{emoji} [{level}]" if emoji else f"[{level}]"
        return f"<strong>{prefix}</strong>"

    return SEVERITY_COLOR_RE.sub(_replacer, text)


def ocr_result_path() -> str:
    return os.environ.get("OCR_RESULT_PATH", "/tmp/ocr-result.json")


def ocr_stderr_path() -> str:
    return os.environ.get("OCR_STDERR_PATH", "/tmp/ocr-stderr.log")


def post_strict_enabled() -> bool:
    """Gateway 设置 OCR_POST_STRICT=1；ocr-ci CI Job 不设（解析失败仍 exit 0）。"""
    return os.environ.get("OCR_POST_STRICT", "").lower() in ("1", "true", "yes")


def failure_note_body(parse_error: str, stderr_content: str) -> str:
    if stderr_content:
        return f"⚠️ **OpenCodeReview** encountered an error:\n```\n{stderr_content}\n```"
    return (
        "⚠️ **OpenCodeReview** failed: could not read review output "
        f"({parse_error}). Check the `ocr review` step in the job log."
    )


class GitLabMrClient:
    """GitLab MR API 最小客户端：Note 与行内讨论。"""

    def __init__(
        self,
        *,
        gitlab_url: str,
        project_id: str,
        mr_iid: str,
        api_token: str | None = None,
        retry_base_delay: float = 2.0,
        max_retries: int = 3,
        max_retry_delay: float = 60.0,
        success_delay: float = 2.0,
        failure_delay: float = 1.0,
        rate_limit_threshold: int = 10,
    ) -> None:
        self.gitlab_url = gitlab_url.rstrip("/")
        self.project_id = project_id
        self.mr_iid = mr_iid
        baked = resolve_gitlab_api_token()
        self.api_token = api_token or os.environ.get("GITLAB_API_TOKEN") or baked or os.environ.get(
            "CI_JOB_TOKEN", ""
        )
        self.retry_base_delay = retry_base_delay
        self.max_retries = max_retries
        self.max_retry_delay = max_retry_delay
        self.success_delay = success_delay
        self.failure_delay = failure_delay
        self.rate_limit_threshold = rate_limit_threshold
        self.transient_base_delay = 2.0
        self._api_base = (
            f"{self.gitlab_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}"
        )
        self._auth_header = (
            "JOB-TOKEN"
            if not (api_token or os.environ.get("GITLAB_API_TOKEN") or baked)
            else "PRIVATE-TOKEN"
        )

    @classmethod
    def from_env(cls) -> GitLabMrClient:
        return cls(
            gitlab_url=os.environ.get("CI_SERVER_URL", "https://gitlab.com"),
            project_id=os.environ["CI_PROJECT_ID"],
            mr_iid=os.environ["CI_MERGE_REQUEST_IID"],
            retry_base_delay=int(os.environ.get("OCR_RETRY_BASE_DELAY", "2000")) / 1000,
            max_retries=int(os.environ.get("OCR_MAX_RETRIES", "3")),
            max_retry_delay=int(os.environ.get("OCR_MAX_RETRY_DELAY", "60000")) / 1000,
            success_delay=int(os.environ.get("OCR_SUCCESS_DELAY", "2000")) / 1000,
            failure_delay=int(os.environ.get("OCR_FAILURE_DELAY", "1000")) / 1000,
            rate_limit_threshold=int(os.environ.get("OCR_RATE_LIMIT_THRESHOLD", "10")),
        )

    def _get_header(self, headers: Any, name: str) -> str | None:
        if name in headers:
            val = headers[name]
        elif name.lower() in headers:
            val = headers[name.lower()]
        else:
            return None
        return str(val).strip() if val is not None else None

    def _parse_rate_limit_header(self, headers: Any, name: str) -> int | None:
        val = self._get_header(headers, name)
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    def api_request_with_retry(
        self, endpoint: str, data: dict | None = None, method: str = "POST"
    ) -> dict[str, Any]:
        if not self.api_token:
            return {"success": False, "data": None, "is_rate_limit_exhausted": False}

        for attempt in range(self.max_retries + 1):
            url = f"{self._api_base}{endpoint}"
            headers = {
                self._auth_header: self.api_token,
                "Content-Type": "application/json",
            }
            body = json.dumps(data).encode("utf-8") if data else None
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    raw = resp.read().decode("utf-8")
                    resp_data = json.loads(raw) if raw else {}
                    remaining = self._parse_rate_limit_header(resp.headers, "RateLimit-Remaining")
                    return {
                        "success": True,
                        "data": resp_data,
                        "is_rate_limit_exhausted": False,
                        "rate_limit_remaining": remaining,
                    }
            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8")
                is_rate_limit = e.code == 429 or (
                    e.code == 403
                    and any(
                        kw in error_body.lower()
                        for kw in ["retry later", "rate limit", "too many requests", "abuse"]
                    )
                )
                is_transient = (500 <= e.code < 600) or e.code == 408
                rl_remaining = self._parse_rate_limit_header(e.headers, "RateLimit-Remaining")
                if (is_rate_limit or is_transient) and attempt < self.max_retries:
                    retry_after = self._get_header(e.headers, "Retry-After")
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            delay = self.retry_base_delay * (2**attempt)
                    elif is_transient:
                        delay = self.transient_base_delay * (2**attempt)
                    else:
                        delay = self.retry_base_delay * (2**attempt)
                    delay = min(delay, self.max_retry_delay)
                    delay = delay * (0.75 + random.random() * 0.5)
                    time.sleep(delay)
                else:
                    return {
                        "success": False,
                        "data": None,
                        "is_rate_limit_exhausted": is_rate_limit,
                        "rate_limit_remaining": rl_remaining,
                    }
        return {
            "success": False,
            "data": None,
            "is_rate_limit_exhausted": False,
            "rate_limit_remaining": None,
        }

    def post_note(self, body: str) -> dict[str, Any]:
        return self.api_request_with_retry("/notes", {"body": body})

    def post_discussion(
        self, path: str, line: int, body: str, base_sha: str, start_sha: str, head_sha: str
    ) -> dict[str, Any]:
        position = {
            "position_type": "text",
            "new_path": path,
            "old_path": path,
            "new_line": line,
            "base_sha": base_sha,
            "start_sha": start_sha,
            "head_sha": head_sha,
        }
        return self.api_request_with_retry("/discussions", {"body": body, "position": position})

    def fetch_mr_versions(self) -> dict[str, str] | None:
        resp = self.api_request_with_retry("/versions", method="GET")
        if not resp.get("success"):
            return None
        versions = resp.get("data") or []
        if not versions:
            return None
        latest = versions[0]
        return {
            "base_sha": latest.get("base_commit_sha", ""),
            "start_sha": latest.get("start_commit_sha", ""),
            "head_sha": latest.get("head_commit_sha", ""),
        }


def post_review_from_files(
    client: GitLabMrClient,
    result_path: str | None = None,
    stderr_path: str | None = None,
) -> int:
    """将 result_path 的 OCR JSON 发帖到 MR。返回进程退出码（0=CI 成功）。"""
    strict = post_strict_enabled()
    any_post_ok = False
    result_path = result_path or ocr_result_path()
    stderr_path = stderr_path or ocr_stderr_path()

    def record(resp: dict[str, Any]) -> None:
        nonlocal any_post_ok
        if resp.get("success"):
            any_post_ok = True

    try:
        with open(result_path, encoding="utf-8") as f:
            result = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        stderr_content = ""
        try:
            with open(stderr_path, encoding="utf-8") as f:
                stderr_content = f.read().strip()
        except FileNotFoundError:
            pass
        record(client.post_note(failure_note_body(str(e), stderr_content)))
        return 1 if strict and not any_post_ok else 0

    comments = result.get("comments", [])
    warnings = result.get("warnings", [])

    if not comments:
        message = result.get("message", "No comments generated. Looks good to me.")
        record(client.post_note(f"✅ **OpenCodeReview**: {message}"))
        return 1 if strict and not any_post_ok else 0

    diff_refs = client.fetch_mr_versions()
    success_count = 0
    failed_comments: list[dict] = []

    for comment in comments:
        path = comment.get("path", "")
        end_line = comment.get("end_line", 0)
        body = _format_comment(comment)
        if not path or not end_line or not diff_refs:
            failed_comments.append(comment)
            continue
        result_resp = client.post_discussion(path, end_line, body, **diff_refs)
        record(result_resp)
        if result_resp.get("success"):
            success_count += 1
            time.sleep(client.success_delay)
        else:
            failed_comments.append(comment)
            time.sleep(client.failure_delay)

    if failed_comments:
        fallback_body = (
            "🔍 **OpenCodeReview** found issues that could not be posted inline:\n\n---\n\n"
        )
        for comment in failed_comments:
            fallback_body += _format_comment_fallback(comment) + "\n\n---\n\n"
        record(client.post_note(fallback_body))

    total_count = len(comments)
    failed_count = len(failed_comments)
    summary = f"🔍 **OpenCodeReview** found **{total_count}** issue(s) in this MR."
    if total_count > 0:
        summary += f"\n- ✅ {success_count} posted as inline comment(s)"
        summary += f"\n- 📝 {failed_count} posted as summary (missing line info)"
    if warnings:
        summary += f"\n\n⚠️ {len(warnings)} warning(s) occurred during review."
    record(client.post_note(summary))
    return 1 if strict and not any_post_ok else 0


def _format_comment(comment: dict) -> str:
    body = colorize_severity(comment.get("content", ""))
    existing = comment.get("existing_code", "")
    suggestion = comment.get("suggestion_code", "")
    if suggestion and existing:
        body += "\n\n**Suggestion:**\n"
        body += f"```suggestion:-0+0\n{suggestion}\n```"
    return body


def _format_comment_fallback(comment: dict) -> str:
    path = comment.get("path", "unknown")
    start_line = comment.get("start_line", 0)
    end_line = comment.get("end_line", 0)
    content = colorize_severity(comment.get("content", ""))
    md = f"### 📄 `{path}`"
    if start_line and end_line:
        md += f" (L{start_line}-L{end_line})"
    md += f"\n\n{content}"
    existing = comment.get("existing_code", "")
    suggestion = comment.get("suggestion_code", "")
    if suggestion and existing:
        md += "\n\n<details><summary>💡 Suggested Change</summary>\n\n"
        md += f"**Before:**\n```\n{existing}\n```\n\n"
        md += f"**After:**\n```\n{suggestion}\n```\n\n"
        md += "</details>"
    return md

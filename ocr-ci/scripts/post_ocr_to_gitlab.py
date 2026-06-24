#!/usr/bin/env python3
"""Post OpenCodeReview JSON output to GitLab MR discussions/notes.

Used by GitLab CI OCR pipelines (slim image or bootstrap). Reads:
  /tmp/ocr-result.json  — stdout from `ocr review --format json`
  /tmp/ocr-stderr.log   — stderr from ocr review (on parse failure)

Environment (GitLab CI injects most; optional tuning via CI/CD Variables):
  CI_SERVER_URL, CI_PROJECT_ID, CI_MERGE_REQUEST_IID, CI_COMMIT_SHA
  GITLAB_API_TOKEN or ~/.opencodereview/config.json gitlab.api_token or CI_JOB_TOKEN
  OCR_RETRY_BASE_DELAY, OCR_MAX_RETRIES, OCR_MAX_RETRY_DELAY
  OCR_SUCCESS_DELAY, OCR_FAILURE_DELAY, OCR_RATE_LIMIT_THRESHOLD

See ocr-ci/docs/本地部署指南.md and open-code-review/examples/gitlab_ci/.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))
from ocr_ci_config import resolve_gitlab_api_token


def failure_note_body(parse_error: str, stderr_content: str) -> str:
    """Build MR note when ocr-result.json is missing or invalid."""
    if stderr_content:
        return f"⚠️ **OpenCodeReview** encountered an error:\n```\n{stderr_content}\n```"
    return (
        "⚠️ **OpenCodeReview** failed: could not read review output "
        f"({parse_error}). Check the `ocr review` step in the job log."
    )


def main() -> None:
    # --- GitLab CI context (injected by Runner) ---
    gitlab_url = os.environ.get("CI_SERVER_URL", "https://gitlab.com")
    project_id = os.environ["CI_PROJECT_ID"]
    mr_iid = os.environ["CI_MERGE_REQUEST_IID"]
    # Token priority: env GITLAB_API_TOKEN > baked config > CI_JOB_TOKEN (fork MR fallback)
    baked_gitlab_token = resolve_gitlab_api_token()
    api_token = (
        os.environ.get("GITLAB_API_TOKEN")
        or baked_gitlab_token
        or os.environ.get("CI_JOB_TOKEN", "")
    )

    retry_base_delay = int(os.environ.get("OCR_RETRY_BASE_DELAY", "2000")) / 1000
    max_retries = int(os.environ.get("OCR_MAX_RETRIES", "3"))
    max_retry_delay = int(os.environ.get("OCR_MAX_RETRY_DELAY", "60000")) / 1000
    success_delay = int(os.environ.get("OCR_SUCCESS_DELAY", "2000")) / 1000
    failure_delay = int(os.environ.get("OCR_FAILURE_DELAY", "1000")) / 1000
    transient_base_delay = 2
    rate_limit_threshold = int(os.environ.get("OCR_RATE_LIMIT_THRESHOLD", "10"))

    if not api_token:
        print(
            "ERROR: No API token (GITLAB_API_TOKEN, config.json gitlab.api_token, or CI_JOB_TOKEN). "
            "Cannot post comments.",
            file=sys.stderr,
        )
        sys.exit(1)

    api_base = f"{gitlab_url}/api/v4/projects/{project_id}/merge_requests/{mr_iid}"
    # PAT / Project token use PRIVATE-TOKEN; CI_JOB_TOKEN uses JOB-TOKEN header
    auth_header = "JOB-TOKEN" if not (
        os.environ.get("GITLAB_API_TOKEN") or baked_gitlab_token
    ) else "PRIVATE-TOKEN"

    def _get_header(headers, name):
        if name in headers:
            val = headers[name]
        elif name.lower() in headers:
            val = headers[name.lower()]
        else:
            return None
        return str(val).strip() if val is not None else None

    def _parse_rate_limit_header(headers, name):
        val = _get_header(headers, name)
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return None

    def api_request_with_retry(endpoint, data=None, method="POST"):
        """Call GitLab MR API with exponential backoff on 429/5xx."""
        for attempt in range(max_retries + 1):
            url = f"{api_base}{endpoint}"
            headers = {
                auth_header: api_token,
                "Content-Type": "application/json",
            }
            body = json.dumps(data).encode("utf-8") if data else None
            req = urllib.request.Request(url, data=body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    resp_data = json.loads(resp.read().decode("utf-8"))
                    remaining = _parse_rate_limit_header(resp.headers, "RateLimit-Remaining")
                    limit = _parse_rate_limit_header(resp.headers, "RateLimit-Limit")
                    if remaining is not None and limit is not None:
                        print(
                            f"RateLimit: {remaining}/{limit} remaining for {endpoint}",
                            file=sys.stderr,
                        )
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
                rl_remaining = _parse_rate_limit_header(e.headers, "RateLimit-Remaining")
                if (is_rate_limit or is_transient) and attempt < max_retries:
                    retry_after = _get_header(e.headers, "Retry-After")
                    if retry_after:
                        try:
                            delay = float(retry_after)
                        except ValueError:
                            delay = retry_base_delay * (2**attempt)
                    elif is_transient:
                        delay = transient_base_delay * (2**attempt)
                    else:
                        delay = retry_base_delay * (2**attempt)
                    delay = min(delay, max_retry_delay)
                    delay = delay * (0.75 + random.random() * 0.5)
                    rl_info = (
                        f" (RateLimit-Remaining: {rl_remaining})"
                        if rl_remaining is not None
                        else ""
                    )
                    reason = "rate limit" if is_rate_limit else f"transient error (HTTP {e.code})"
                    print(
                        f"{reason} hit for {endpoint}, retrying in {delay:.1f}s "
                        f"(attempt {attempt + 1}/{max_retries}){rl_info}",
                        file=sys.stderr,
                    )
                    time.sleep(delay)
                else:
                    print(f"API error {e.code}: {error_body}", file=sys.stderr)
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

    def post_note(body):
        return api_request_with_retry("/notes", {"body": body})

    def post_discussion(path, line, body, base_sha, start_sha, head_sha):
        position = {
            "position_type": "text",
            "new_path": path,
            "old_path": path,
            "new_line": line,
            "base_sha": base_sha,
            "start_sha": start_sha,
            "head_sha": head_sha,
        }
        data = {"body": body, "position": position}
        return api_request_with_retry("/discussions", data)

    def format_comment(comment):
        body = comment.get("content", "")
        existing = comment.get("existing_code", "")
        suggestion = comment.get("suggestion_code", "")
        if suggestion and existing:
            body += "\n\n**Suggestion:**\n"
            body += f"```suggestion:-0+0\n{suggestion}\n```"
        return body

    def format_comment_fallback(comment):
        path = comment.get("path", "unknown")
        start_line = comment.get("start_line", 0)
        end_line = comment.get("end_line", 0)
        content = comment.get("content", "")

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

    # --- Parse ocr review JSON from CI job (Linux path /tmp/...) ---
    try:
        with open("/tmp/ocr-result.json", "r", encoding="utf-8") as f:
            result = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Failed to parse OCR output: {e}", file=sys.stderr)
        stderr_content = ""
        try:
            with open("/tmp/ocr-stderr.log", "r", encoding="utf-8") as f:
                stderr_content = f.read().strip()
        except FileNotFoundError:
            pass
        post_note(failure_note_body(str(e), stderr_content))
        # exit 0: allow_failure job stays green; failure visible on MR
        sys.exit(0)

    comments = result.get("comments", [])
    warnings = result.get("warnings", [])

    if not comments:
        message = result.get("message", "No comments generated. Looks good to me.")
        post_note(f"✅ **OpenCodeReview**: {message}")
        print("No review comments to post.")
        sys.exit(0)

    # --- Inline discussions (need MR version SHAs for diff position) ---
    diff_refs = None
    versions_resp = api_request_with_retry("/versions", method="GET")
    if versions_resp and versions_resp.get("success"):
        versions = versions_resp.get("data", [])
        if versions:
            latest = versions[0]
            diff_refs = {
                "base_sha": latest.get("base_commit_sha", ""),
                "start_sha": latest.get("start_commit_sha", ""),
                "head_sha": latest.get("head_commit_sha", ""),
            }
    if not diff_refs:
        print(
            "Warning: Could not fetch MR versions. Inline comments will use fallback.",
            file=sys.stderr,
        )

    success_count = 0
    failed_comments = []

    for comment in comments:
        path = comment.get("path", "")
        end_line = comment.get("end_line", 0)
        body = format_comment(comment)

        if not path or not end_line or not diff_refs:
            failed_comments.append(comment)
            continue

        result_resp = post_discussion(path, end_line, body, **diff_refs)
        if result_resp and result_resp.get("success"):
            success_count += 1
            remaining = result_resp.get("rate_limit_remaining")
            if (
                rate_limit_threshold > 0
                and remaining is not None
                and remaining <= rate_limit_threshold
            ):
                pace_delay = success_delay * 2
                print(
                    f"Rate limit quota low ({remaining} remaining), "
                    f"increasing pacing delay to {pace_delay:.1f}s",
                    file=sys.stderr,
                )
                time.sleep(pace_delay)
            else:
                time.sleep(success_delay)
        else:
            failed_comments.append(comment)
            is_rate_limit_exhausted = (
                result_resp.get("is_rate_limit_exhausted", False) if result_resp else False
            )
            post_fail_delay = success_delay if is_rate_limit_exhausted else failure_delay
            time.sleep(post_fail_delay)

    print(f"Successfully posted {success_count}/{len(comments)} inline comments.")

    if failed_comments:
        fallback_body = (
            "🔍 **OpenCodeReview** found issues that could not be posted inline:\n\n---\n\n"
        )
        for comment in failed_comments:
            fallback_body += format_comment_fallback(comment) + "\n\n---\n\n"
        post_note(fallback_body)

    total_count = len(comments)
    failed_count = len(failed_comments)
    summary = f"🔍 **OpenCodeReview** found **{total_count}** issue(s) in this MR."
    if total_count > 0:
        summary += f"\n- ✅ {success_count} posted as inline comment(s)"
        summary += f"\n- 📝 {failed_count} posted as summary (missing line info)"
    if warnings:
        summary += f"\n\n⚠️ {len(warnings)} warning(s) occurred during review."
    post_note(summary)


if __name__ == "__main__":
    main()

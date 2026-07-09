"""Shared GitLab API helpers for OCR Gateway E2E (ocr-ci2 standalone)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from lib.env_loader import load_dotenv as _load_dotenv_impl
from lib.paths import E2E_ROOT

__all__ = [
    "E2E_ROOT",
    "load_dotenv",
    "gitlab_token",
    "gitlab_url",
    "gateway_url",
    "gateway_secret",
    "api_request",
    "api_get",
    "api_get_all_pages",
    "get_mr_pipelines",
    "get_pipeline_jobs",
    "get_job_trace",
    "get_mr_notes",
    "get_mr_discussions",
    "gateway_get_job",
]


def load_dotenv() -> None:
    _load_dotenv_impl()


def gitlab_token() -> str:
    return (
        os.environ.get("AICR_BOT_TOKEN")
        or os.environ.get("ROOT_PAT")
        or os.environ.get("GITLAB_API_TOKEN")
        or ""
    )


def gitlab_url() -> str:
    return os.environ.get("GITLAB_URL", "http://localhost:8000").rstrip("/")


def gateway_url() -> str:
    return os.environ.get("OCR_GATEWAY_URL", "http://localhost:8010").rstrip("/")


def gateway_secret() -> str:
    value = os.environ.get("OCR_GATEWAY_SECRET", "")
    if value:
        return value
    default = "local-dev-secret"
    if gitlab_url().startswith("http://localhost") or gitlab_url().startswith("http://127.0.0.1"):
        return default
    raise RuntimeError("OCR_GATEWAY_SECRET must be set for non-local GitLab")


def api_request(method: str, url: str, token: str, data: dict | None = None) -> dict | list:
    headers = {"PRIVATE-TOKEN": token, "Content-Type": "application/json"}
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def api_get(url: str, token: str) -> dict | list:
    return api_request("GET", url, token)


def api_get_all_pages(url: str, token: str, *, per_page: int = 100) -> list:
    """Fetch all pages from a GitLab API list endpoint."""
    items: list = []
    page = 1
    while True:
        sep = "&" if "?" in url else "?"
        page_url = f"{url}{sep}page={page}&per_page={per_page}"
        data = api_get(page_url, token)
        if not isinstance(data, list) or not data:
            break
        items.extend(data)
        if len(data) < per_page:
            break
        page += 1
    return items


def get_mr_pipelines(token: str, project_id: int, mr_iid: int) -> list:
    url = f"{gitlab_url()}/api/v4/projects/{project_id}/merge_requests/{mr_iid}/pipelines"
    data = api_get(url, token)
    return data if isinstance(data, list) else []


def get_pipeline_jobs(token: str, project_id: int, pipeline_id: int) -> list:
    url = f"{gitlab_url()}/api/v4/projects/{project_id}/pipelines/{pipeline_id}/jobs"
    data = api_get(url, token)
    return data if isinstance(data, list) else []


def get_job_trace(token: str, project_id: int, job_id: int) -> str:
    url = f"{gitlab_url()}/api/v4/projects/{project_id}/jobs/{job_id}/trace"
    req = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read().decode("utf-8", errors="replace")


def get_mr_notes(token: str, project_id: int, mr_iid: int) -> list:
    base = f"{gitlab_url()}/api/v4/projects/{project_id}/merge_requests/{mr_iid}"
    return api_get_all_pages(f"{base}/notes?sort=desc&order_by=updated_at", token)


def get_mr_discussions(token: str, project_id: int, mr_iid: int) -> list:
    base = f"{gitlab_url()}/api/v4/projects/{project_id}/merge_requests/{mr_iid}"
    try:
        return api_get_all_pages(f"{base}/discussions", token)
    except urllib.error.HTTPError:
        return []


def gateway_get_job(job_id: str) -> dict:
    url = f"{gateway_url()}/v1/jobs/{job_id}"
    req = urllib.request.Request(
        url,
        headers={"X-OCR-Gateway-Token": gateway_secret()},
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))

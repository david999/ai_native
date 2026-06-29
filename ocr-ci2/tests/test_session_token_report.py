"""session_token_report.py 单元测试。"""

from __future__ import annotations

import json
from pathlib import Path

from session_telemetry import scan_session_jsonl
from session_token_report import render_csv, render_markdown


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, ensure_ascii=False) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _sample_session(tmp_path: Path, session_id: str, prompt: int, completion: int) -> Path:
    repo = tmp_path / "repo,group,proj-111"
    jsonl = repo / f"{session_id}.jsonl"
    _write_jsonl(
        jsonl,
        [
            {
                "type": "session_start",
                "sessionId": session_id,
                "cwd": "/work/datacalc-web",
                "gitBranch": "feat/test",
            },
            {
                "type": "llm_response",
                "usage": {
                    "prompt_tokens": prompt,
                    "completion_tokens": completion,
                    "cache_read_tokens": 0,
                },
            },
            {
                "type": "session_end",
                "files_reviewed": 1,
                "duration_seconds": 42.5,
                "llm_failures": 0,
            },
        ],
    )
    return jsonl


def test_scan_session_jsonl_token_usage(tmp_path: Path):
    jsonl = _sample_session(tmp_path, "sess001", 100_000, 8_000)
    result = scan_session_jsonl(jsonl)
    assert result.tokens.prompt_tokens == 100_000
    assert result.tokens.completion_tokens == 8_000
    assert result.tokens.total == 108_000
    assert result.tokens.request_count == 1
    assert result.files_reviewed == 1
    assert result.duration_seconds == 42.5


def test_render_markdown_sorted_by_total(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("OCR_SESSIONS_DIR", str(tmp_path))
    low = scan_session_jsonl(_sample_session(tmp_path, "low-sess", 10_000, 1_000))
    high = scan_session_jsonl(_sample_session(tmp_path, "high-sess", 200_000, 20_000))

    md = render_markdown([low, high], top=None)
    assert "200,000" in md
    assert md.index("200,000") < md.index("11,000")


def test_render_csv_top_limit(tmp_path: Path):
    low = scan_session_jsonl(_sample_session(tmp_path, "low-sess", 10_000, 1_000))
    high = scan_session_jsonl(_sample_session(tmp_path, "high-sess", 200_000, 20_000))

    csv_text = render_csv([low, high], top=1)
    lines = [line for line in csv_text.strip().splitlines() if line]
    assert len(lines) == 2  # header + one row
    assert "high-sess" in csv_text
    assert "low-sess" not in csv_text

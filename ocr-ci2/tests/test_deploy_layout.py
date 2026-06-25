"""deploy/ 布局冒烟测试 — 关键文件存在性。

覆盖：local、prod/native、prod/docker、prod/ci 文件齐全。
不测：执行 install.ps1；校验注释正文。
"""
from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

DEPLOY_FILES = [
    "deploy/README.md",
    "deploy/local/install.ps1",
    "deploy/local/run.ps1",
    "deploy/local/gateway.env.example",
    "deploy/prod/native/install.sh",
    "deploy/prod/native/run.sh",
    "deploy/prod/native/gateway.env.example",
    "deploy/prod/native/ocr-gateway.service.example",
    "deploy/prod/docker/Dockerfile",
    "deploy/prod/docker/docker-compose.yml",
    "deploy/prod/docker/build_image.ps1",
    "deploy/prod/docker/run.ps1",
    "deploy/prod/docker/gateway.env.example",
    "deploy/prod/ci/snippet.native-host.yml",
    "deploy/prod/ci/snippet.docker.yml",
]


def test_deploy_layout_key_files_exist():
    missing = [rel for rel in DEPLOY_FILES if not (REPO_ROOT / rel).is_file()]
    assert not missing, f"missing deploy files: {missing}"

#!/usr/bin/env python3
"""将 OpenCodeReview JSON 输出发帖到 GitLab MR 讨论/Note。

从 OCR_RESULT_PATH / OCR_STDERR_PATH 读取路径（默认 /tmp/ocr-result.json）。

逻辑清单：
- Token：GitLabMrClient.from_env()（config.json、GITLAB_API_TOKEN、CI_JOB_TOKEN）
- 退出码：无 token 时非零；strict 模式由环境变量 OCR_POST_STRICT 控制
- 不做：执行 ocr review；解析 CLI 参数（仅 env 入口）
"""

from __future__ import annotations

import sys

from gitlab_mr import GitLabMrClient, post_review_from_files


def main() -> None:
    client = GitLabMrClient.from_env()
    if not client.api_token:
        print(
            "ERROR: No API token (GITLAB_API_TOKEN, config.json gitlab.api_token, or CI_JOB_TOKEN).",
            file=sys.stderr,
        )
        sys.exit(1)
    sys.exit(post_review_from_files(client))


if __name__ == "__main__":
    main()

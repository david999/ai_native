# Demo / 联调工程（test_data）

本目录用于放置 **独立的 Git 业务仓库**，与 monorepo（`E:\ai_native`）分离版本管理，用于 GitLab MR + CI 全链路联调。

## 预期布局

```
test_data/
└── spring-cloud-demo/     # 示例 Spring Cloud 工程（自有 .git）
    ├── .gitlab-ci.yml
    ├── .llm/CONTEXT.md
    └── scripts/
        └── run_review.py  # 可选；推荐改用 ci_review_gate.sh
```

当前目录可能为空：将 Demo 克隆或复制到此处即可，**不要求**纳入本 monorepo 的 Git 历史（根 `.gitignore` 已忽略 `test_data/**/.git/`）。

## 获取 Demo

若已有远程 GitLab 仓库：

```bash
cd test_data
git clone http://localhost:8000/java_group/spring-cloud-demo.git
```

或从其他路径复制现有工程到 `test_data/spring-cloud-demo/`。

## CI 集成（推荐）

在业务仓库 `.gitlab-ci.yml` 中引用 AICR 门禁脚本，示例见：

- [`aicr-reviewer/ci/gitlab-ci.snippet.yml`](../aicr-reviewer/ci/gitlab-ci.snippet.yml)
- [docs/CI_REVIEW_PIPELINE.md](../docs/CI_REVIEW_PIPELINE.md)

核心 job 调用 `aicr-reviewer/scripts/ci_review_gate.sh`，向评审服务 `POST /review`；**仅当** `review_completed=true` 且分数低于阈值时失败 job。

### GitLab CI/CD Variables（业务仓库）

| 变量 | 说明 |
|------|------|
| `AICR_REVIEW_URL` | 如 `http://aicr-reviewer:8001`（Runner 网络内） |
| `AICR_REVIEW_SECRET` | 与 `evn/.env` 中 `REVIEW_API_SECRET` 一致 |
| `AICR_SCORE_THRESHOLD` | 默认 `60` |

## 项目规范文件

Demo 仓库根目录可放置 **`.llm/CONTEXT.md`**，评审时注入 LLM system prompt（团队架构规范）。

## 全链路验收

见 [docs/LOCAL_PC_VERIFICATION.md](../docs/LOCAL_PC_VERIFICATION.md) L3 章节。

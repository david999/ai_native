# AI Native — AICR 代码评审

本仓库包含 **AICR Reviewer**（基于 LLM 的 GitLab MR 自动代码评审服务）及其本地/生产运行环境配置。

## 仓库结构

```
.
├── aicr-reviewer/          # FastAPI 评审服务（核心应用）
│   ├── app/                # API、GitLab 集成、LLM、评审流水线
│   ├── deploy/             # Docker Compose 叠加配置
│   ├── scripts/            # 本地启动与冒烟测试
│   └── README.md           # 服务级运行与 API 说明
├── docs/                   # 架构与密钥管理文档（见 docs/README.md）
├── evn/                    # 环境配置（见 evn/README.md）
│   ├── .env.example        # 环境变量模板
│   ├── .aicr/              # config.toml 模板（阶段 C）
│   └── gitlab/             # GitLab CE + Runner 编排
└── test_data/              # Demo 工程（见 test_data/README.md，可选）
```

## 回归阅读顺序

1. [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) — 工程全景与重点关注
2. [docs/LOCAL_PC_VERIFICATION.md](docs/LOCAL_PC_VERIFICATION.md) — L1–L3 分层验收
3. [docs/ACCEPTANCE_TESTING.md](docs/ACCEPTANCE_TESTING.md) — 一键验收与多模板对比

## 快速开始

1. 复制环境变量：`cp evn/.env.example evn/.env`，按 [docs/SECRETS.md](docs/SECRETS.md) 填写密钥。
2. 本地启动服务：见 [aicr-reviewer/README.md](aicr-reviewer/README.md) 中的 `scripts/run_local.sh`。
3. 健康检查：`GET http://localhost:8001/health`
4. 冒烟测试：`cd aicr-reviewer && python scripts/smoke_test.py`（Windows 与分层验收见 [docs/LOCAL_PC_VERIFICATION.md](docs/LOCAL_PC_VERIFICATION.md)）

## 文档索引

| 文档 | 说明 |
|------|------|
| [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md) | **工程全景**（回归首选） |
| [docs/ACCEPTANCE_TESTING.md](docs/ACCEPTANCE_TESTING.md) | 一键验收、fixtures、结果落盘 |
| [docs/README.md](docs/README.md) | **文档地图**、代码↔文档映射表 |
| [evn/README.md](evn/README.md) | 环境目录、Compose 启动、gitignore 边界 |
| [test_data/README.md](test_data/README.md) | Demo 独立 Git、CI 集成 |
| [docs/LOCAL_PC_VERIFICATION.md](docs/LOCAL_PC_VERIFICATION.md) | **本地 PC**：测试命令、启动服务、L1–L3 整体验收 |
| [docs/TESTING.md](docs/TESTING.md) | 冒烟用例覆盖矩阵与 fail-open 说明 |
| [docs/CI_REVIEW_PIPELINE.md](docs/CI_REVIEW_PIPELINE.md) | **CI 流水线**：reviewdog + AICR、增量评审与阶段 A 配置 |
| [aicr-reviewer/README.md](aicr-reviewer/README.md) | 运行方式、API、失败策略 |
| [docs/LLM_CODE_REVIEW.md](docs/LLM_CODE_REVIEW.md) | **大模型如何实现代码评审**（流程、提示词、接入与门禁） |
| [docs/PROMPT_TEMPLATES.md](docs/PROMPT_TEMPLATES.md) | 多版本提示词模板与对比测试 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构与评审流水线 |
| [docs/CODE_REFERENCE.md](docs/CODE_REFERENCE.md) | **源码级详细说明**（模块、分支、数据结构） |
| [docs/GITHUB_REFERENCES.md](docs/GITHUB_REFERENCES.md) | **外部开源参考**（pr-agent / ai-pr-reviewer / reviewdog 与阶段 A/B/C 落点） |
| [docs/PHASE_C.md](docs/PHASE_C.md) | 阶段 C：describe、CHANGELOG、评论对话、config.toml |
| [docs/SECRETS.md](docs/SECRETS.md) | 密钥与环境变量说明 |

## 评审触发方式

- **CI**：Runner 执行 `aicr-reviewer/scripts/ci_review_gate.sh`（内部 `POST /review`）；仅 `review_completed=true` 且分数低于阈值时失败 job。示例见 `aicr-reviewer/ci/gitlab-ci.snippet.yml`。
- **Webhook**：GitLab MR 事件 `POST /webhook/gitlab`（需配置 `GITLAB_WEBHOOK_SECRET`）。

详细流程见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

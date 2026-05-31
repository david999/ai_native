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
├── docs/                   # 架构与密钥管理文档
├── evn/                    # 环境配置（.env 模板、GitLab Compose）
│   ├── .env.example        # 环境变量模板
│   └── gitlab/             # GitLab CE + Runner 编排
└── test_data/              # Demo 工程（可选，用于 MR 联调）
```

## 快速开始

1. 复制环境变量：`cp evn/.env.example evn/.env`，按 [docs/SECRETS.md](docs/SECRETS.md) 填写密钥。
2. 本地启动服务：见 [aicr-reviewer/README.md](aicr-reviewer/README.md) 中的 `scripts/run_local.sh`。
3. 健康检查：`GET http://localhost:8001/health`
4. 冒烟测试：`cd aicr-reviewer && python scripts/smoke_test.py`

## 文档索引

| 文档 | 说明 |
|------|------|
| [aicr-reviewer/README.md](aicr-reviewer/README.md) | 运行方式、API、失败策略 |
| [docs/LLM_CODE_REVIEW.md](docs/LLM_CODE_REVIEW.md) | **大模型如何实现代码评审**（流程、提示词、接入与门禁） |
| [docs/LLM_CODE_REVIEW.html](docs/LLM_CODE_REVIEW.html) | 同上（HTML 阅读版，含目录导航） |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 系统架构与评审流水线 |
| [docs/CODE_REFERENCE.md](docs/CODE_REFERENCE.md) | **源码级详细说明**（模块、分支、数据结构） |
| [docs/SECRETS.md](docs/SECRETS.md) | 密钥与环境变量说明 |
| [docs/GITHUB_ACCESS_CN_MOBILE.md](docs/GITHUB_ACCESS_CN_MOBILE.md) | **国内手机（华为/安卓）访问 GitHub**（Cursor Cloud 场景，已筛选可行方案） |

## 评审触发方式

- **CI**：Runner 执行 `aicr-reviewer/scripts/ci_review_gate.sh`（内部 `POST /review`）；仅 `review_completed=true` 且分数低于阈值时失败 job。示例见 `aicr-reviewer/ci/gitlab-ci.snippet.yml`。
- **Webhook**：GitLab MR 事件 `POST /webhook/gitlab`（需配置 `GITLAB_WEBHOOK_SECRET`）。

详细流程见 [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

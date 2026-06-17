# AI Native — AICR 代码评审

本仓库包含 **AICR Reviewer**（基于 LLM 的 GitLab MR 自动代码评审服务）及其本地/生产运行环境配置。

## 仓库结构

```
.
├── aicr-reviewer/          # FastAPI 评审服务（核心应用）
├── docs/                   # 项目文档（见 docs/文档索引.md）
├── evn/                    # 环境配置（见 evn/README.md）
└── test_data/              # Demo 工程与 fixtures
```

## 回归阅读顺序

1. [docs/工程全景.md](docs/工程全景.md) — 工程定位与踩坑清单
2. [docs/测试与验收.md](docs/测试与验收.md) — 分层验收与冒烟测试
3. [docs/L3发版验收.md](docs/L3发版验收.md) — 发版签收（L3-full）

## 快速开始

1. 复制环境变量：`cp evn/.env.example evn/.env`，按 [docs/环境变量与密钥.md](docs/环境变量与密钥.md) 填写密钥。
2. 启动服务：见 [aicr-reviewer/README.md](aicr-reviewer/README.md)。
3. 冒烟测试：`cd aicr-reviewer && python scripts/smoke_test.py`
4. 日常验收：`.\scripts\run_acceptance.ps1 -Level daily`

## 文档索引

| 文档 | 说明 |
|------|------|
| [docs/文档索引.md](docs/文档索引.md) | **文档地图**、代码↔文档映射表 |
| [docs/工程全景.md](docs/工程全景.md) | 工程全景（回归首选） |
| [docs/测试与验收.md](docs/测试与验收.md) | L1–L3 验收、冒烟矩阵 |
| [docs/L3发版验收.md](docs/L3发版验收.md) | L3-full 发版门禁 |
| [docs/系统架构.md](docs/系统架构.md) | 系统架构与评审流水线 |
| [docs/大模型评审说明.md](docs/大模型评审说明.md) | LLM 评审流程与提示词 |
| [docs/源码参考.md](docs/源码参考.md) | 源码级详细说明 |
| [docs/环境变量与密钥.md](docs/环境变量与密钥.md) | 密钥与环境变量 |
| [aicr-reviewer/README.md](aicr-reviewer/README.md) | API 与运行方式 |

## 评审触发方式

- **CI**：Runner 执行 `ci_review_gate.sh`（内部 `POST /review`）
- **Webhook**：GitLab MR 事件 `POST /webhook/gitlab`

详细流程见 [docs/系统架构.md](docs/系统架构.md)。

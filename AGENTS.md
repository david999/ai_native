# AGENTS.md

本文件为 AI 编码助手提供仓库级指引。

## 项目概览

**AICR Reviewer**：基于 FastAPI 的 GitLab MR 自动代码评审服务（Python 3 + pip）。核心代码在 `aicr-reviewer/`；共享环境变量在 `evn/.env`（从 `evn/.env.example` 复制，勿提交真实密钥）。

## Documentation sync

改 **行为 / API / 配置 / CI** 相关代码时，须在同一任务内更新对应 Markdown（见 [docs/README.md](docs/README.md) 映射表）。

- Cursor 规则：[`.cursor/rules/docs-sync.mdc`](.cursor/rules/docs-sync.mdc)（全局）、[`docs-sync-aicr-reviewer.mdc`](.cursor/rules/docs-sync-aicr-reviewer.mdc)、[`docs-sync-evn.mdc`](.cursor/rules/docs-sync-evn.mdc)
- 新增 env var → `evn/.env.example` + `docs/SECRETS.md`
- 改 `scripts/smoke_test.py` → `docs/TESTING.md`
- 验收：`cd aicr-reviewer && python scripts/smoke_test.py`

## Cursor Cloud specific instructions

### 开发与验证（无需 Docker）

| 步骤 | 命令 |
|------|------|
| 依赖 | `cd aicr-reviewer && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` |
| 冒烟测试 | `cd aicr-reviewer && source .venv/bin/activate && python scripts/smoke_test.py`（覆盖见 `docs/TESTING.md`；本地 PC 验收见 `docs/LOCAL_PC_VERIFICATION.md`） |
| 启动 API | `./scripts/run_local.sh` 或 `python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload`（工作目录为 `aicr-reviewer/`） |
| 健康检查 | `curl http://localhost:8001/health` |

### 环境变量

- 配置路径：`evn/.env`（仓库根目录下的 `evn/`，非 `env`）。
- 本地快速启动可复制模板：`cp evn/.env.example evn/.env`；完整说明见 `docs/SECRETS.md`。
- 无 GitLab / 无 LLM 密钥时仍可跑冒烟测试；`POST /review` 需要有效的 `AICR_BOT_TOKEN`、`GITLAB_URL` 及 `LLM_API_KEY` 等。

### 系统依赖（Ubuntu / Debian Cloud VM）

若 `python3 -m venv` 报错 `ensurepip is not available`，需一次性安装：

```bash
sudo apt-get install -y python3.12-venv
```

本仓库**无**根级 Makefile、无 ESLint/Ruff 配置；语法检查可用 `python -m compileall -q aicr-reviewer/app aicr-reviewer/main.py`。

### 可选：GitLab + Docker 全链路 E2E

需要 Docker 与外部网络 `gitlab_default`：

1. `docker network create gitlab_default`（若不存在）
2. `cd evn/gitlab && docker compose -f docker-compose.yml up -d`
3. 构建并叠加启动 reviewer：见 `aicr-reviewer/README.md` 中 Linux Docker 部署一节

Cloud Agent 默认镜像可能未预装 Docker；仅验证应用逻辑时优先使用冒烟测试 + 本地 uvicorn。

### 服务端口

| 服务 | 端口 |
|------|------|
| AICR Reviewer | 8001 |
| GitLab CE（可选） | 8000 |

### 长时间运行

开发服务器请用 tmux 启动（例如会话名 `aicr-reviewer-dev`），避免阻塞单次 shell 调用。

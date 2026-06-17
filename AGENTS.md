# AGENTS.md

本文件为 AI 编码助手提供仓库级指引。

## 项目概览

**AICR Reviewer**：基于 FastAPI 的 GitLab MR 自动代码评审服务（Python 3 + pip）。核心代码在 `aicr-reviewer/`；共享环境变量在 `evn/.env`（从 `evn/.env.example` 复制，勿提交真实密钥）。

## Documentation sync

改 **行为 / API / 配置 / CI** 相关代码时，须在同一任务内更新对应 Markdown（见 [docs/文档索引.md](docs/文档索引.md) 映射表）。

- Cursor 规则：[`.cursor/rules/docs-sync.mdc`](.cursor/rules/docs-sync.mdc)（全局）、[`docs-sync-aicr-reviewer.mdc`](.cursor/rules/docs-sync-aicr-reviewer.mdc)、[`docs-sync-evn.mdc`](.cursor/rules/docs-sync-evn.mdc)
- 新增 env var → `evn/.env.example` + `docs/环境变量与密钥.md`
- 改 `scripts/smoke_test.py` → `docs/测试与验收.md`
- 验收：`cd aicr-reviewer && python scripts/smoke_test.py`

## Cursor Cloud specific instructions

### 开发与验证（无需 Docker）

| 步骤 | 命令 |
|------|------|
| 依赖 | `cd aicr-reviewer && python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt` |
| 冒烟测试 | `cd aicr-reviewer && source .venv/bin/activate && python scripts/smoke_test.py`（覆盖见 `docs/测试与验收.md`；本地 PC 验收见 `docs/测试与验收.md`） |
| 日常验收 | `cd aicr-reviewer && .\scripts\run_acceptance.ps1 -Level daily`（L1+L2，中文报告，**无需 Docker**） |
| 读最新报告 | `python scripts/show_latest_report.py`（见 `docs/测试与验收.md`） |
| 启动 API | `./scripts/run_local.sh` 或 `python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload`（工作目录为 `aicr-reviewer/`） |
| 健康检查 | `curl http://localhost:8001/health` |

### 环境变量

- 配置路径：`evn/.env`（仓库根目录下的 `evn/`，非 `env`）。
- 本地快速启动可复制模板：`cp evn/.env.example evn/.env`；完整说明见 `docs/环境变量与密钥.md`。
- 无 GitLab / 无 LLM 密钥时仍可跑冒烟测试；`POST /review` 需要有效的 `AICR_BOT_TOKEN`、`GITLAB_URL` 及 `LLM_API_KEY` 等。

### 系统依赖（Ubuntu / Debian Cloud VM）

若 `python3 -m venv` 报错 `ensurepip is not available`，需一次性安装：

```bash
sudo apt-get install -y python3.12-venv
```

本仓库**无**根级 Makefile、无 ESLint/Ruff 配置；语法检查可用 `python -m compileall -q aicr-reviewer/app aicr-reviewer/main.py`。

### 本地验收（默认不依赖 Docker）

1. **日常**：`run_acceptance.ps1 -Level daily` → 读 `show_latest_report.py`
2. **L3**：用户手动启动本机 GitLab 后 `run_acceptance.ps1 -Level L3`
3. **可选生产 Docker**：见 `evn/gitlab/docker-compose.yml`（部署方式待定，与本地 daily 验收无关）

### 服务端口

| 服务 | 端口 |
|------|------|
| AICR Reviewer | 8001 |
| GitLab CE（可选） | 8000 |

### 长时间运行

开发服务器请用 tmux 启动（例如会话名 `aicr-reviewer-dev`），避免阻塞单次 shell 调用。

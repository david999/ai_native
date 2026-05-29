# AICR Reviewer

LLM-powered code review service for GitLab MRs.

## 运行方式

| 环境 | 方式 | 说明 |
|------|------|------|
| **本地开发（Windows/Linux，无 Docker）** | `scripts/run_local.ps1` 或 `scripts/run_local.sh` | 直接 Python + uvicorn |
| **生产部署（Linux + Docker）** | `deploy/docker-compose.aicr-reviewer.yml` | 容器化运行，接入 GitLab 内网 |

## 本地开发（无 Docker）

### 1. 配置 `.env`

在项目根目录 `E:\ai_native\.env` 中设置（参见 `SECRETS.md`）：

```bash
AICR_BOT_TOKEN=glpat-...
GITLAB_URL=http://localhost:8000
LLM_PROVIDER=ctyun_openai
LLM_API_BASE=https://wishub-x6.ctyun.cn/v1
LLM_API_KEY=<天翼云服务组 AppKey>
LLM_MODEL=<模型 ID>
```

### 2. 安装依赖并启动

**Windows (PowerShell):**

```powershell
cd E:\ai_native\aicr-reviewer
.\scripts\run_local.ps1
```

**Linux / macOS:**

```bash
cd aicr-reviewer
chmod +x scripts/run_local.sh
./scripts/run_local.sh
```

服务监听 `http://localhost:8001`，健康检查：`GET /health`

### 3. 手动触发评审

```powershell
curl -X POST http://localhost:8001/review `
  -H "Content-Type: application/json" `
  -d '{"project_id": 2, "mr_iid": 1}'
```

### 4. 冒烟测试（无需 LLM key）

```bash
python scripts/smoke_test.py
```

## 生产部署（Linux + Docker）

在 Linux 服务器上，GitLab 与 Runner 已通过 Docker 运行时：

```bash
cd /path/to/ai_native/aicr-reviewer
docker build -t gitlab-aicr-reviewer:latest .

cd /path/to/ai_native/gitlab
docker compose -f docker-compose.yml -f ../aicr-reviewer/deploy/docker-compose.aicr-reviewer.yml up -d aicr-reviewer
```

容器内 `GITLAB_URL=http://gitlab:8000`（Docker 网络），CI 通过 `http://aicr-reviewer:8001/review` 调用。

## API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/review` | POST | CI 触发评审 `{project_id, mr_iid}` |
| `/webhook/gitlab` | POST | GitLab Webhook（可选） |

## 项目规范注入

评审时自动加载仓库中的 `.llm/CONTEXT.md`（源分支优先，目标分支回退）。

## 架构

```
app/
├── api/routes.py          # FastAPI 路由
├── gitlab/
│   ├── context_builder.py # MR 变更 + CONTEXT.md
│   └── publisher.py       # 行内评论 / MR note 降级
├── llm/
│   ├── openai_compat.py   # OpenAI 兼容 API（天翼云/DeepSeek/智谱）
│   └── factory.py
└── review/
    ├── orchestrator.py    # 评审编排
    ├── chunker.py         # diff 分块
    ├── parser.py          # JSON 解析
    └── prompts/           # Jinja2 模板
```

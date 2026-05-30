# AICR Reviewer

基于 LLM 的 GitLab Merge Request 自动代码评审服务。

更多说明见仓库根目录 [README.md](../README.md)、[docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md)。

## 运行方式

| 环境 | 方式 |
|------|------|
| **本地开发（无 Docker）** | `scripts/run_local.ps1` / `scripts/run_local.sh` |
| **Linux 生产（Docker）** | `evn/gitlab` + `deploy/docker-compose.aicr-reviewer.yml` |

## 配置

密钥与变量放在 **`evn/.env`**（见 `evn/.env.example`、`docs/SECRETS.md`）。

```bash
# evn/.env 关键项
GITLAB_URL=http://localhost:8000          # 本地；Docker 内为 http://gitlab:8000
AICR_BOT_TOKEN=glpat-...
LLM_API_KEY=...
LLM_MODEL=...
REVIEW_API_SECRET=...                     # 可选；CI 用 X-AICR-Secret
```

## 本地启动

```powershell
cd E:\ai_native\aicr-reviewer
.\scripts\run_local.ps1
```

健康检查：`GET http://localhost:8001/health`

冒烟测试：`python scripts/smoke_test.py`

## Linux Docker 部署

```bash
cd aicr-reviewer && docker build -t gitlab-aicr-reviewer:latest .
cd ../evn/gitlab
docker compose -f docker-compose.yml \
  -f ../../aicr-reviewer/deploy/docker-compose.aicr-reviewer.yml \
  up -d aicr-reviewer
```

## Demo 工程

`test_data/spring-cloud-demo/` — 推送到 GitLab 后 MR 触发 CI review。

## API

| 端点 | 说明 |
|------|------|
| `GET /health` | 健康检查 |
| `POST /review` | CI 触发；Header `X-AICR-Secret`（若配置了 `REVIEW_API_SECRET`） |
| `POST /webhook/gitlab` | 需 `GITLAB_WEBHOOK_SECRET` |

## 失败策略

| 场景 | HTTP | CI |
|------|------|-----|
| 评审服务异常（LLM/GitLab/网络/超时/配置等） | 200 + score=100 | fail-open（通过） |
| 低分 | 200 + score | fail-close |
| 无可审文件 | 200 + score=100 | 通过 |
| 鉴权失败 | 401 | 失败（非评审异常） |

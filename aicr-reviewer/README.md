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

`POST /review` 响应字段：

| 字段 | 说明 |
|------|------|
| `score` | 0–100；未实际评审时为占位 100 |
| `review_completed` | `true` 表示 LLM 已完成评审；**仅此时 CI 才应按分数拦 MR** |
| `summary` | 摘要；跳过评审时含 `fail-open` |

## GitLab CI 门禁（Runner 侧）

将 `scripts/ci_review_gate.sh` 复制到业务仓库，或在流水线中引用本仓库路径，示例见 `ci/gitlab-ci.snippet.yml`。

```yaml
aicr-review:
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"
  script:
    - bash path/to/ci_review_gate.sh
  variables:
    AICR_REVIEW_URL: "http://your-aicr-host:8001"
```

脚本逻辑：**仅当** `review_completed=true` **且** `score < AICR_SCORE_THRESHOLD` 时 `exit 1`；HTTP 非 200、curl 失败、鉴权失败、`review_completed=false` 等均放行。

## 失败策略

| 场景 | API | Runner 门禁 |
|------|-----|----------------|
| 鉴权/LLM/GitLab/网络/超时/配置等异常 | 200，`review_completed=false` | 通过 |
| 无可审文件 | 200，`review_completed=false` | 通过 |
| 评审完成且低分 | 200，`review_completed=true`，低分 | **失败** |
| 评审完成且达标 | 200，`review_completed=true`，高分 | 通过 |

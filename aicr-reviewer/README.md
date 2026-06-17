# AICR Reviewer

基于 LLM 的 GitLab Merge Request 自动代码评审服务。

更多说明见仓库根目录 [README.md](../README.md)、[docs/系统架构.md](../docs/系统架构.md)。

## 运行方式

| 环境 | 方式 |
|------|------|
| **本地开发（无 Docker）** | `scripts/run_local.ps1` / `scripts/run_local.sh` |
| **Linux 生产（Docker）** | `evn/gitlab` + `deploy/docker-compose.aicr-reviewer.yml` |

## 配置

密钥与变量放在 **`evn/.env`**（见 `evn/.env.example`、`docs/环境变量与密钥.md`）。

```bash
# evn/.env 关键项
GITLAB_URL=http://localhost:8000          # 本地；Docker 内为 http://gitlab:8000
AICR_BOT_TOKEN=glpat-...
LLM_API_KEY=...
LLM_MODEL=...
REVIEW_API_SECRET=...                     # 生产必填；CI 用 X-AICR-Secret
REVIEW_API_ALLOW_INSECURE=0               # 仅本地：无 secret 时允许 /review
```

启动 uvicorn 时会在日志中输出 Review API 鉴权模式（便于发现误开 `REVIEW_API_ALLOW_INSECURE`）。

## 本地启动

```powershell
cd E:\ai_native\aicr-reviewer
.\scripts\run_local.ps1
```

健康检查：`GET http://localhost:8001/health`

冒烟测试：`python scripts/smoke_test.py`（用例矩阵 [docs/测试与验收.md](../docs/测试与验收.md)）

一键验收：`.\scripts\run_acceptance.ps1 -Level all`（[docs/测试与验收.md](../docs/测试与验收.md)）

## Linux Docker 部署

```bash
cd aicr-reviewer && docker build -t gitlab-aicr-reviewer:latest .
cd ../evn/gitlab
docker compose -f docker-compose.yml \
  -f ../../aicr-reviewer/deploy/docker-compose.aicr-reviewer.yml \
  up -d aicr-reviewer
```

## Demo 工程

见 [test_data/README.md](../test_data/README.md)。预期路径 `test_data/spring-cloud-demo/`（独立 Git）；目录可能为空，克隆 Demo 后推送到 GitLab 即可 MR 联调。

## API

| 端点 | 说明 |
|------|------|
| `GET /health` | 健康检查（仅 `status`） |
| `GET /health/detail` | 详细配置探测（含 `review_dry_run`、`llm_key_set` 等；内网/运维/L3 preflight 用） |
| `POST /review` | CI 触发；Header `X-AICR-Secret`（若配置了 `REVIEW_API_SECRET`） |
| `POST /describe` | 生成 MR 描述（阶段 C，见 [docs/阶段C扩展能力.md](../docs/阶段C扩展能力.md)） |
| `POST /changelog` | 生成 CHANGELOG 并发布 MR note |
| `POST /webhook/gitlab` | MR + **Note** 事件；需 `GITLAB_WEBHOOK_SECRET` |

`POST /review` 响应字段：

| 字段 | 说明 |
|------|------|
| `score` | 0–100；未实际评审时为占位 100 |
| `review_completed` | `true` 表示 LLM 已完成评审；**仅此时 CI 才应按分数拦 MR** |
| `summary` | 摘要；跳过评审时含 `fail-open` |
| `system_template` | 实际应用的 system 模板路径（如 `variants/system_spring_v2_strict.j2`） |
| `system_template_requested` | 请求中的 `system_template`（未指定则为空） |
| `prompt_sha256` | 渲染后 system prompt 的 SHA-256 |

可选请求体字段 `system_template`（须在白名单内，见 `prompts/variants/manifest.yaml`）覆盖 env `AICR_SYSTEM_TEMPLATE`；非法值返回 **400**。`PromptRenderer.render_system_text()` 为仅返回文本的兼容包装。详见 [docs/提示词模板.md](../docs/提示词模板.md)。

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
| 未配置 `REVIEW_API_SECRET` 且未开 `REVIEW_API_ALLOW_INSECURE` | **503** | 通过（脚本视为 fail-open） |

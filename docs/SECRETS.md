# 密钥与环境变量

所有敏感配置放在 **`evn/.env`**（勿提交 Git）。模板见 [`evn/.env.example`](../evn/.env.example)。

## 必填项（评审正常运行）

| 变量 | 说明 |
|------|------|
| `AICR_BOT_TOKEN` | GitLab Bot/PAT，用于读 MR、发评论 |
| `GITLAB_URL` | GitLab 根 URL；本地 `http://localhost:8000`，Docker 网络内常为 `http://gitlab:8000` |
| `LLM_API_KEY` | LLM 服务 API Key |
| `LLM_MODEL` | 模型名称（如 `deepseek-chat`） |

## 推荐项

| 变量 | 说明 |
|------|------|
| `REVIEW_API_SECRET` | CI 调用 `POST /review` 时 Header `X-AICR-Secret`；生产必填 |
| `REVIEW_API_ALLOW_INSECURE` | 仅本地：`1` 且未配置 secret 时允许 `/review`（会打 warning） |
| `GITLAB_TIMEOUT_SECONDS` | GitLab API 超时（秒），默认 `30` |
| `GITLAB_API_RETRIES` | GitLab API 失败重试次数，默认 `3` |
| `REVIEW_MAX_CONCURRENT` | 最大并发评审数，默认 `2` |
| `GITLAB_WEBHOOK_SECRET` | Webhook `X-Gitlab-Token` 校验；生产务必设置 |
| `AICR_SCORE_THRESHOLD` | 通过分数线，默认 `60` |

## LLM 相关

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `LLM_PROVIDER` | `ctyun_openai` | 预设：`ctyun_openai`、`deepseek`、`zhipu`、`openai` |
| `LLM_API_BASE` | 随 provider | 可覆盖预设 endpoint |
| `LLM_TIMEOUT_SECONDS` | `120` | 请求超时 |
| `LLM_MAX_TOKENS` | `4096` | 单次 completion 上限 |
| `LLM_TEMPERATURE` | `0.2` | 采样温度 |

## 评审行为

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `REVIEW_MAX_INPUT_TOKENS` | `12000` | 每块 diff 估算 token 上限 |
| `CONTEXT_MAX_CHARS` | `8000` | `.llm/CONTEXT.md` 截断长度 |
| `REVIEW_DRY_RUN` | `0` | `1` 时不向 GitLab 发评论，仅返回 API 结果 |

## Webhook 调试

| 变量 | 说明 |
|------|------|
| `GITLAB_WEBHOOK_ALLOW_INSECURE` | 仅本地：`1` 且未配置 secret 时允许 Webhook（会打 warning） |

## 安全实践

1. **不要**将 `evn/.env`、Runner `config.toml`、GitLab `gitlab-secrets.json` 提交到 Git（已在根 `.gitignore` 排除）。
2. 评审前会对 diff、上下文、**MR 描述**及 CI 注入的 `extra_diff` 做 **脱敏**（`app/utils/redact.py`）；标题保持原文便于 LLM 理解变更意图，但仍应避免在标题中粘贴真实密钥。
3. 生产环境务必设置 `REVIEW_API_SECRET` 与 `GITLAB_WEBHOOK_SECRET`。
4. `ROOT_PAT` 仅用于 GitLab 初始化/管理，与 Bot Token 职责分离。

## 本地与 Docker 差异

- 本地：`GITLAB_URL=http://localhost:8000`
- Docker Compose 同网络：`GITLAB_URL=http://gitlab:8000`（服务名解析）

Compose 可通过 `env_file: ../../evn/.env` 注入变量，详见 `aicr-reviewer/deploy/docker-compose.aicr-reviewer.yml`。

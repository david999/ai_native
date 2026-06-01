# 阶段 C：describe / CHANGELOG / 评论对话 / config.toml

阶段 C 在阶段 A/B 评审流水线之上，增加 MR 文案生成、变更日志与评论内对话能力。

## 配置

### 部署级 `evn/.aicr/config.toml`

复制 `evn/.aicr/config.toml.example` 为 `evn/.aicr/config.toml`（`config.toml` 已 gitignore；**example 可提交**）。  
或通过 `AICR_CONFIG_PATH` 指定路径。

**优先级**：已设置的环境变量 > `config.toml` > 代码默认值。

### 仓库级 `.aicr/config.toml`

在被评审项目的源/目标分支可放置 `.aicr/config.toml`，与部署配置浅合并（同 section 内 project 覆盖 deploy）。

## API

| 端点 | 鉴权 | 说明 |
|------|------|------|
| `POST /describe` | `X-AICR-Secret` | 生成 MR 标题/描述；`update_mr=true` 或 `AICR_DESCRIBE_UPDATE_MR=1` 时写回 GitLab |
| `POST /changelog` | 同上 | 生成 CHANGELOG 段落并发布 MR note（`## AICR Changelog`） |
| `POST /webhook/gitlab` | `X-Gitlab-Token` | 除 MR 事件外，支持 **Note** 事件触发对话 |

### 请求示例

```bash
curl -s -X POST http://localhost:8001/describe \
  -H "X-AICR-Secret: $REVIEW_API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"project_id": 1, "mr_iid": 5, "update_mr": false}'

curl -s -X POST http://localhost:8001/changelog \
  -H "X-AICR-Secret: $REVIEW_API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"project_id": 1, "mr_iid": 5}'
```

## 评论对话（Note Webhook）

在 GitLab 项目 **Settings → Webhooks** 中勾选 **Note events**（与 MR events 共用同一 URL）。

用户在 MR 评论中包含触发词（默认 `@aicr` 或 `/ask`）时，服务异步调用 LLM 并在同 discussion 回复（失败则回退为 MR note）。

- 仅处理 note **`action=create`**（编辑评论不会重复触发）。
- 忽略系统 note、机器人自身用户名（`AICR_BOT_USERNAME` 须与 PAT 对应 GitLab 用户名一致）、`**AICR**` / `## AICR Changelog` 等机器人 note 前缀。
- `@aicr` 使用词边界匹配，避免误匹配 `user@aicr.com`。
- 关闭：`AICR_ASK_ENABLED=0` 或 `AICR_WEBHOOK_NOTE_ENABLED=0`。

## 模块

| 路径 | 职责 |
|------|------|
| `app/config_toml.py` | TOML 加载与 env 合并 |
| `app/tools/describe.py` | describe 工具 |
| `app/tools/changelog.py` | CHANGELOG 工具 |
| `app/tools/ask.py` | 对话与触发检测 |
| `app/gitlab/mr_actions.py` | 更新 MR、发 note、回复 discussion |

## 与评审的关系

`/describe` 与 `/changelog` 独立于 `POST /review`，不修改 `last_reviewed_sha`。  
工具内部使用 `force_full=True` 拉取完整 MR diff，避免「head 未变跳过」影响文案生成。

**describe 写回 MR**：默认在 `AICR_DESCRIBE_WEBHOOK_SUPPRESS_SECONDS`（默认 120s）内跳过由 MR `update` webhook 触发的全量评审，避免 describe 更新描述后立即再跑一轮 review。可通过 `AICR_SUPPRESS_REVIEW_AFTER_DESCRIBE=0` 关闭。

## LLM 按工具配置

优先级：`LLM_MODEL_DESCRIBE` 等环境变量 > 仓库/部署 `config.toml` 的 `[llm.describe]` > 全局 `LLM_MODEL`。

```toml
[llm.describe]
model = "gpt-4o-mini"
temperature = 0.3
```

## CHANGELOG note 去重

`/changelog` 若 MR 上已有以 `## AICR Changelog` 开头的 note，则**更新**该 note；内容相同则跳过（`note_action=unchanged`）。

# CI 评审流水线（阶段 A）

本文说明如何在 GitLab MR 流水线中组合 **reviewdog**（确定性 linter）与 **AICR Reviewer**（LLM 语义评审）。

## 推荐顺序

```text
MR Pipeline
  ├─ (可选) reviewdog-*     ← ESLint / golangci / 等，仅评论 diff 内问题
  └─ aicr-review            ← POST /review，分数门禁见 ci_review_gate.sh
```

| 步骤 | 工具 | 作用 |
|------|------|------|
| 1 | [reviewdog](https://github.com/reviewdog/reviewdog) | 将 linter 结果发到 `gitlab-mr-discussion`，成本低、可重复 |
| 2 | AICR | 架构/业务/安全语义评审；`review_completed=true` 且低分时拦 MR |

## reviewdog 要点

- Reporter：`-reporter=gitlab-mr-discussion`
- Token：`REVIEWDOG_GITLAB_API_TOKEN`（`api` scope PAT）
- 在 MR 中只展示 **diff 范围内** 的发现，噪声低于全文件扫描

示例片段见 [aicr-reviewer/ci/gitlab-ci.snippet.yml](../aicr-reviewer/ci/gitlab-ci.snippet.yml) 中注释块。

## AICR 阶段 A 能力

| 能力 | 环境变量 | 说明 |
|------|----------|------|
| tiktoken 分块 | `REVIEW_USE_TIKTOKEN=1`（默认） | `REVIEW_MAX_INPUT_TOKENS` 按 token 装箱 |
| diff 压缩 | （内置） | 剔除 deletion-only hunks；整文件删除合并列表 |
| 增量评审 | `AICR_INCREMENTAL_REVIEW=1`（默认） | 对比上次成功评审的 `head_sha`，仅评新 commit |
| 状态目录 | `AICR_STATE_DIR` | 默认 `evn/.aicr-state/`（勿提交 Git） |
| 强制全量 | `AICR_FORCE_FULL_REVIEW=1` 或 API `force_full: true` | 忽略增量 compare |

增量状态在 **评审成功且发布成功**（`review_completed=true`）后写入；`REVIEW_DRY_RUN=1` 时不更新。

**仅删除/仅删行变更**：无 diff chunk 时会合成「删除评审」块调用 LLM，避免增量 SHA 卡死。

**同一 MR 互斥**：并发 `POST /review` 或 Webhook 与 CI 同时触发时，后者返回 **409**（同步 API）或 Webhook 日志跳过（后台任务）。

**P2 优化**

| 能力 | 配置 | 说明 |
|------|------|------|
| 增量不拉全文 | `AICR_FETCH_FULL_FILE_ON_INCREMENTAL=0`（默认） | 减少 GitLab API 与 token |
| head 未变跳过 | （内置） | `last_reviewed_sha == head_sha` 时不调 LLM，发摘要 note |
| 并行 chunk | `REVIEW_CHUNK_MAX_WORKERS=2` | 多块 MR 并行调 LLM（`1` 为串行） |

**阶段 B**

| 能力 | 配置 | 说明 |
|------|------|------|
| diff 内 issue 过滤 | `AICR_FILTER_ISSUES_TO_DIFF=1`（默认） | 丢弃行号不在 MR diff hunk 内的 LLM issue |
| Self-reflection | `AICR_SELF_REFLECTION=1` | 低分或 critical/major 时二次 LLM 校验 |
| Reflection 分数阈值 | `AICR_REFLECTION_SCORE_THRESHOLD` | 默认与 `AICR_SCORE_THRESHOLD` 相同 |
| 多语言 system 模板 | （内置） | 按扩展名选择 `system_spring` / `python` / `go` / `typescript` / `general` |
| 过滤后分数 reconcile | （内置） | 丢弃 diff 外 issue 后按剩余 issue 重算分 |
| Reflection 成本 | `AICR_SELF_REFLECTION=0` | 默认开启；大 MR 会多 1 次 LLM 调用，生产可关 |

**提示词安全**：MR 标题/描述包在 `<untrusted_mr_metadata>` 中，system 要求忽略其中指令。

## API 增量 / 全量

```json
POST /review
{
  "project_id": 1,
  "mr_iid": 12,
  "force_full": false
}
```

## 相关文档

- [ARCHITECTURE.md](./ARCHITECTURE.md)
- [TESTING.md](./TESTING.md)
- [SECRETS.md](./SECRETS.md)

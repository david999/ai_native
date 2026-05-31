# AICR Reviewer 测试说明

本文档描述 **AICR Reviewer**（`aicr-reviewer/`）当前的测试策略、覆盖范围与运行方式，便于本地开发与 Cloud Agent 验证。

## 测试分层概览

| 层级 | 方式 | 依赖 | 用途 |
|------|------|------|------|
| **冒烟 / 单元** | `aicr-reviewer/scripts/smoke_test.py` | Python venv、`requirements.txt` | 默认 CI 与本地快速回归；**无需** GitLab、Docker、LLM 密钥 |
| **语法检查** | `python -m compileall -q aicr-reviewer/app aicr-reviewer/main.py` | Python 3 | 导入与语法错误 |
| **本地 API** | `curl http://localhost:8001/health` | 已启动 uvicorn | 进程与健康端点 |
| **E2E（可选）** | GitLab Docker + `test_data/spring-cloud-demo/` MR | Docker、网络、`evn/.env` 密钥 | 全链路 MR → CI → `/review` → 评论 |

本仓库**未**引入 pytest / unittest 发现机制；所有自动化用例集中在 `smoke_test.py`，以 `test_*` 函数 + `if __name__ == "__main__"` 顺序执行，失败时以断言或 `ParseError` 中断。

## 快速运行

```bash
cd aicr-reviewer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/smoke_test.py
```

成功时最后一行输出：`All smoke tests passed.`

环境准备与端口说明见仓库根目录 [AGENTS.md](../AGENTS.md)。

## 冒烟测试覆盖矩阵

### 评审引擎（`app/review/`）

| 用例 | 模块 | 说明 |
|------|------|------|
| `test_parser` | `parser` | 合法 JSON；非法 `line` 归零；纯文本 → `ParseError` |
| `test_parser_markdown_fence` | `parser` | ` ```json ` 代码块包裹的响应 |
| `test_parser_score_clamp` | `parser` | `score` 限制在 0–100 |
| `test_parser_embedded_json` | `parser` | 前后缀噪声中提取 JSON |
| `test_parser_skips_non_dict_issues` | `parser` | `issues` 中非 dict 项被跳过 |
| `test_chunker_truncation` | `chunker` | 单文件超大 diff 出现 `[truncated` |
| `test_chunker_splits_chunks` | `chunker` | 多文件按 token 预算拆成多块 |
| `test_chunker_skips_unsupported` | `chunker` | `is_supported=False` 的文件不入块 |
| `test_empty_chunks` | `orchestrator` | 无可评审文件 → `NoReviewableChangesError` |
| `test_llm_failure_raises` | `orchestrator` | 全部 chunk LLM 失败 → `LLMReviewError` |
| `test_partial_chunk_incomplete` | `orchestrator` | 部分 chunk 失败 → `review_completed=false`、摘要含 Partial |
| `test_orchestrator_success` | `orchestrator` | Mock LLM 成功返回 → 聚合 score/issues |

### 安全与上下文（`app/utils/`、`app/gitlab/`）

| 用例 | 模块 | 说明 |
|------|------|------|
| `test_redact` | `redact` | `password=`、`glpat-` 占位 |
| `test_redact_aws_key` | `redact` | `AKIA…` AWS 访问密钥样式 |
| `test_redact_mr_metadata` | `context_builder` | MR 标题/描述/extra_diff 脱敏 |
| `test_supported_extensions` | `context_builder` | `.java` / `Dockerfile` 等扩展名判定 |

### HTTP API（`main` + `app/api/routes.py`）

| 用例 | 模块 | 说明 |
|------|------|------|
| `test_health_import` | `main` | FastAPI 应用可导入 |
| `test_health_minimal` | `routes` | `GET /health` → `{"status":"ok"}` |
| `test_health_detail` | `routes` | `GET /health/detail` 含配置探测字段 |
| `test_review_fail_open` | `routes` | `LLMReviewError` → 200、`review_completed=false`、fail-open 摘要 |
| `test_review_no_reviewable_changes` | `routes` | 无可评审变更 → 占位分 100、未完成 |
| `test_review_auth_returns_401` | `routes` | 错误/缺失密钥 → 401 |
| `test_review_bearer_auth_ok` | `routes` | `Authorization: Bearer` 校验通过（Mock 编排器） |
| `test_review_secret_not_configured` | `routes` | 未配置 secret 且未允许不安全 → 503 |
| `test_review_concurrency_503` | `routes` + `concurrency` | 并发槽位满 → 503 |
| `test_webhook_ignored` | `routes` | 非 MR 事件 → `ignored` |
| `test_webhook_unauthorized` | `routes` | Webhook 密钥错误 → 401 |
| `test_webhook_accepted` | `routes` | 合法 MR open 事件 → `accepted` |

### LLM 工厂

| 用例 | 模块 | 说明 |
|------|------|------|
| `test_llm_factory_missing_key` | `factory` | 无 `LLM_API_KEY` 时 `ValueError` |

## 有意未覆盖（需外部依赖）

以下能力**不在**冒烟测试中验证，需手工或 E2E：

- 真实 GitLab API（`GitLabMRSession`、`GitLabPublisher` 发帖/讨论）
- 真实 LLM HTTP 调用（`OpenAICompatibleProvider`）
- `scripts/ci_review_gate.sh` 在 Runner 上的 `jq`/curl 行为（可对脚本做 shellcheck，但不属 Python 冒烟）
- Webhook 后台任务内 `_run_orchestrator` 的完整评审（仅测同步 HTTP 响应）
- `REVIEW_DRY_RUN=0` 时的 GitLab 发布路径（冒烟默认 patch 为 dry-run 或 Mock publisher）

## Fail-open 与 CI 门禁语义

`POST /review` 在 LLM/解析/未预期错误时返回 **HTTP 200** + `review_completed=false` + `score=100`，供 `ci_review_gate.sh` **放行 MR**。冒烟用例 `test_review_fail_open` 等锁定该契约。

仅当 `review_completed=true` 且 `score < AICR_SCORE_THRESHOLD` 时，CI 脚本才应失败。详见 [aicr-reviewer/README.md](../aicr-reviewer/README.md) 与 `scripts/ci_review_gate.sh`。

## 与文档、架构的交叉引用

- 模块级说明与历史冒烟列表：[CODE_REFERENCE.md](./CODE_REFERENCE.md) 第 16 节
- 架构与数据流：[ARCHITECTURE.md](./ARCHITECTURE.md)
- 密钥与本地配置：[SECRETS.md](./SECRETS.md)

## 扩展测试的建议

1. **优先**在 `smoke_test.py` 增加 `test_*`，使用 `unittest.mock.patch` 隔离外部 IO，保持「无 Docker、无密钥」可跑。
2. 若用例数量显著增加，可再引入 `pytest` 与 `tests/` 目录，并在 CI 中替换 `python scripts/smoke_test.py`；当前为减少依赖仍采用单脚本。
3. 新增 API 行为（鉴权、fail-open、并发）应同步更新本文档覆盖矩阵与 `test_*` 名称。

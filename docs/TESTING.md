# AICR Reviewer 测试说明

本文档描述 **AICR Reviewer**（`aicr-reviewer/`）当前的测试策略、覆盖范围与运行方式，便于本地开发与 Cloud Agent 验证。

> **在本地 PC 上怎么跑测试、怎么分层验收整个工程？** 见 **[LOCAL_PC_VERIFICATION.md](./LOCAL_PC_VERIFICATION.md)**（含 Windows / Linux 命令与 L1–L3 验收清单）。

## 测试分层概览

| 层级 | 方式 | 依赖 | 用途 |
|------|------|------|------|
| **冒烟 / 单元** | `aicr-reviewer/scripts/smoke_test.py` | Python venv、`requirements.txt` | 默认 CI 与本地快速回归；**无需** GitLab、Docker、LLM 密钥 |
| **语法检查** | `python -m compileall -q aicr-reviewer/app aicr-reviewer/main.py` | Python 3 | 导入与语法错误 |
| **本地 API** | `curl http://localhost:8001/health` | 已启动 uvicorn | 进程与健康端点 |
| **E2E（可选）** | GitLab Docker + `test_data/spring-cloud-demo/` MR | Docker、网络、`evn/.env` 密钥 | 全链路 MR → CI → `/review` → 评论 |

本仓库**未**引入 pytest / unittest 发现机制；所有自动化用例集中在 `smoke_test.py`，以 `test_*` 函数 + `if __name__ == "__main__"` 顺序执行，失败时以断言或 `ParseError` 中断。

## 快速运行

**Linux / macOS / Git Bash：**

```bash
cd aicr-reviewer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/smoke_test.py
```

**Windows PowerShell：**

```powershell
cd aicr-reviewer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\smoke_test.py
```

成功时最后一行输出：`All 78 smoke tests passed.`（数量以 `smoke_test.py` 内 `tests` 列表为准）。

可选 JSON + 中文 Markdown：`python scripts/smoke_test.py --report-json ../test-results/l1-smoke.json`（同时生成 `l1-smoke.md`）

更完整的本地环境说明、服务启动与 **L1/L2/L3 整体验收** 见 [LOCAL_PC_VERIFICATION.md](./LOCAL_PC_VERIFICATION.md)。端口与 Cloud 开发见 [AGENTS.md](../AGENTS.md)。

## 冒烟测试覆盖矩阵

### 解析与分块（`app/review/parser.py`、`chunker.py`）

| 用例 | 说明 |
|------|------|
| `test_parser` | 合法 JSON；非法 `line` 归零；纯文本 → `ParseError` |
| `test_parser_markdown_fence` | ` ```json ` 代码块包裹的响应 |
| `test_parser_score_clamp` | `score` 限制在 0–100 |
| `test_parser_embedded_json` | 前后缀噪声中提取 JSON |
| `test_parser_skips_non_dict_issues` | `issues` 中非 dict 项被跳过 |
| `test_chunker_truncation` | 单文件超大 diff 出现 `[truncated` |
| `test_chunker_splits_chunks` | 多文件按 token 预算拆成多块 |
| `test_chunker_skips_unsupported` | `is_supported=False` 的文件不入块 |
| `test_chunker_single_tokenize_per_file` | 单文件只 tokenize 一次 |

### 阶段 A/B 流水线（`orchestrator`、`diff_compress`、`review_state` 等）

| 用例 | 说明 |
|------|------|
| `test_empty_chunks` | 无可评审文件 → `NoReviewableChangesError` |
| `test_llm_failure_raises` | 全部 chunk LLM 失败 → `LLMReviewError` |
| `test_partial_chunk_incomplete` | 部分 chunk 失败 → `review_completed=false`、摘要含 Partial |
| `test_orchestrator_success` | Mock LLM 成功返回 → 聚合 score/issues |
| `test_orchestrator_filters_out_of_diff` | diff hunk 外 issue 被过滤 |
| `test_orchestrator_skip_unchanged_sha` | head 未变时跳过 LLM |
| `test_orchestrator_parallel_chunks` | 多块并行 LLM |
| `test_orchestrator_deletions_only` | 仅删除变更合成评审块 |
| `test_diff_compress_*`（3 项） | deletion-only hunk、删行、整文件删除 |
| `test_language_priority_sort` | 扩展名频率排序 |
| `test_review_state_store` | `last_reviewed_sha` 持久化 |
| `test_token_utils_fallback` | 关闭 tiktoken 时字符估算 |
| `test_should_fetch_full_file` | 增量是否拉全文 |
| `test_diff_line_index` | diff hunk 行号索引 |
| `test_reconcile_score_after_filter` | 过滤后分数 reconcile |
| `test_should_reflect` / `test_should_reflect_all_issues_filtered` | reflection 触发条件 |
| `test_reflection_includes_diff_text` | reflection prompt 含 diff |
| `test_resolve_system_template` / `test_prompt_renderer_multilang` / `test_prompt_variant_override` | 多语言 system 模板与 variants 覆盖 |
| `test_prompt_untrusted_metadata` | MR 元数据防注入边界 |
| `test_paths_match_strict` / `test_filter_deleted_paths_allowed` | diff 过滤路径匹配 |

### 安全与上下文（`app/utils/`、`app/gitlab/`）

| 用例 | 说明 |
|------|------|
| `test_redact` | `password=`、`glpat-` 占位 |
| `test_redact_aws_key` | `AKIA…` AWS 访问密钥样式 |
| `test_redact_mr_metadata` | MR 标题/描述/extra_diff 脱敏 |
| `test_supported_extensions` | `.java` / `Dockerfile` 等扩展名判定 |

### HTTP API（`main` + `app/api/routes.py`）

| 用例 | 说明 |
|------|------|
| `test_health_import` | FastAPI 应用可导入 |
| `test_health_minimal` | `GET /health` → `{"status":"ok"}` |
| `test_health_detail` | `GET /health/detail` 含配置探测字段 |
| `test_review_fail_open` | `LLMReviewError` → 200、`review_completed=false`、fail-open 摘要 |
| `test_review_no_reviewable_changes` | 无可评审变更 → 占位分 100、未完成 |
| `test_review_auth_returns_401` | 错误/缺失密钥 → 401 |
| `test_review_bearer_auth_ok` | `Authorization: Bearer` 校验通过（Mock 编排器） |
| `test_review_secret_not_configured` | 未配置 secret 且未允许不安全 → **503** |
| `test_review_concurrency_503` | 并发槽位满 → 503 |
| `test_mr_review_lock` / `test_review_mr_busy_409` | 同一 MR 并发 → 409 |
| `test_webhook_ignored` | 非 MR 事件 → `ignored` |
| `test_webhook_unauthorized` | Webhook 密钥错误 → 401 |
| `test_webhook_accepted` | 合法 MR open 事件 → `accepted` |
| `test_webhook_review_suppressed` | describe 后短时抑制 review webhook |

### 阶段 C（`config_toml`、`tools/*`、Note webhook）

| 用例 | 说明 |
|------|------|
| `test_config_toml_merge` | 部署 TOML 与 env 合并 |
| `test_should_respond_to_note` / `test_extract_user_question` | Note 触发词与提问提取 |
| `test_tool_parser_describe` / `test_tool_parser_changelog_ask` | 工具 JSON 解析 |
| `test_describe_prompt_untrusted` | describe 模板防注入 |
| `test_webhook_note_*`（4 项） | Note create/ignore/update、后台 ask |
| `test_note_ask_background_calls_run_ask` | Note 异步 ask |
| `test_describe_disabled_503` | describe 关闭 → 503 |
| `test_diff_text_truncation` | 工具 diff 截断 |
| `test_llm_settings_for_tool` / `test_create_llm_for_tool` | 按工具 LLM 配置 |
| `test_changelog_upsert_note` | CHANGELOG note 去重更新 |
| `test_describe_tool_mock` | describe 写回 MR + webhook 抑制 |

### L3 矩阵脚本（`prompt_matrix_test.py`）

| 用例 | 说明 |
|------|------|
| `test_prompt_matrix_template_ok` | 503 / fail-open / 成功完成 判定 |
| `test_prompt_matrix_exit_code` | 全通过 exit 0；部分失败或无模板 exit 1 |

### LLM 工厂

| 用例 | 说明 |
|------|------|
| `test_llm_factory_missing_key` | 无 `LLM_API_KEY` 时 `ValueError` |

## 有意未覆盖（需外部依赖）

以下能力**不在**冒烟测试中验证，需手工或 E2E：

- 真实 GitLab API（`GitLabMRSession`、`GitLabPublisher` 发帖/讨论）
- 真实 LLM HTTP 调用（`OpenAICompatibleProvider`）
- `scripts/ci_review_gate.sh` 在 Runner 上的 `jq`/curl 行为（可对脚本做 shellcheck，但不属 Python 冒烟）
- Webhook 后台任务内完整评审（仅测同步 HTTP 响应与 Mock 路径）
- `REVIEW_DRY_RUN=0` 时的 GitLab 发布路径（冒烟默认 patch 为 dry-run 或 Mock publisher）

## Fail-open 与 CI 门禁语义

`POST /review` 在 LLM/解析/未预期错误时返回 **HTTP 200** + `review_completed=false` + `score=100`，供 `ci_review_gate.sh` **放行 MR**。冒烟用例 `test_review_fail_open` 等锁定该契约。

未配置 `REVIEW_API_SECRET` 且未设 `REVIEW_API_ALLOW_INSECURE=1` 时返回 **503**；`ci_review_gate.sh` 将非 200 视为 fail-open 放行。

仅当 `review_completed=true` 且 `score < AICR_SCORE_THRESHOLD` 时，CI 脚本才应失败。详见 [aicr-reviewer/README.md](../aicr-reviewer/README.md) 与 `scripts/ci_review_gate.sh`。

## 与文档、架构的交叉引用

| 文档 | 说明 |
|------|------|
| [docs/README.md](./README.md) | 文档地图与代码↔文档映射 |
| [LOCAL_PC_VERIFICATION.md](./LOCAL_PC_VERIFICATION.md) | 本地 PC 跑测试、启动服务、L1–L3 验收清单 |
| [CODE_REFERENCE.md](./CODE_REFERENCE.md) | 源码级说明 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 系统架构与数据流 |
| [SECRETS.md](./SECRETS.md) | 密钥与本地配置 |

## 扩展测试的建议

1. **优先**在 `smoke_test.py` 增加 `test_*`，使用 `unittest.mock.patch` 隔离外部 IO，保持「无 Docker、无密钥」可跑。
2. 若用例数量显著增加，可再引入 `pytest` 与 `tests/` 目录，并在 CI 中替换 `python scripts/smoke_test.py`；当前为减少依赖仍采用单脚本。
3. 新增 API 行为（鉴权、fail-open、并发）应同步更新本文档覆盖矩阵与 `test_*` 名称。

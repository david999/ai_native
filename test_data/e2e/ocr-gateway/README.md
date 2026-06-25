# OCR Gateway + datacalc-web 本地 E2E 自动化

在 **ai_native monorepo** 内一键跑通：场景注入 → push → MR → GitLab CI `code-review` → OCR Gateway → MR 评论。

## 前置条件

1. 本地 GitLab（`:8000`）、Runner、OCR Gateway（`:8010`）已启动
2. `~/.opencodereview/config.json` 含有效 LLM 与 `gitlab.api_token`
3. GitLab 已配置 `OCR_GATEWAY_SECRET`（至少一条 **非 Protected**）
4. `evn/.env` 或环境变量含 `AICR_BOT_TOKEN` / `ROOT_PAT`

跑前检查（自动调用，**OCR Gateway 专用**，跳过 AICR `:8001`）：

```powershell
cd test_data/scripts
.\verify_l3b_runner.ps1 -ProjectPath java_group/datacalc-web -OcrGatewayOnly
```

## 快速开始

```powershell
cd test_data/e2e/ocr-gateway
pip install -r requirements-dev.txt

# 单元测试（见下方「单元测试 pytest」）；不依赖 GitLab/Gateway/LLM
python -m pytest -q

# 全链路 E2E（需 GitLab :8000 + Runner + Gateway :8010 + LLM）
.\run_e2e.ps1 -Scenario D01_feature_date_guard
.\run_e2e.ps1 -All
.\run_e2e.ps1 -All -SkipPreflight
```

## 单元测试（pytest）

在 **`test_data/e2e/ocr-gateway`** 目录执行：

```powershell
python -m pytest -q
```

| 项 | 说明 |
|----|------|
| **测什么** | `tests/test_e2e_helpers.py`：场景 manifest 解析、MR 评论收集、Gateway job_id 解析、**JSONL session 解析**、`assert_ocr_*` 逻辑 |
| **不测什么** | 不 push 代码、不调 GitLab/Gateway/LLM；**不能**代替 D05/D06 全链路验收 |
| **依赖** | `pip install -r requirements-dev.txt`（pytest、PyYAML） |
| **与 E2E 关系** | pytest = 改 Python 辅助代码后的快速回归；`run_e2e.ps1` = 真实 OCR 评审流水线 |

常用变体：`python -m pytest -q --tb=short`（失败看栈）；`python -m pytest --collect-only -q`（只列用例）。

## 场景

| ID | 类型 | 说明 |
|----|------|------|
| `D01_feature_date_guard` | 功能开发 | 换电起止时间顺序校验 |
| `D02_bug_npe_optional` | Bug 引入 | `Optional.orElse(null)` 未校验 |
| `D03_bug_empty_catch` | Bug 引入 | 空 `catch` 吞异常 |
| `D04_bugfix_npe_guard` | Bug 修复 | 补 null guard |
| `D05_rule_severity_prefix` | rule.json R2 | 严重级别前缀 `[HIGH]/[MEDIUM]/[LOW]` |
| `D06_rule_ai_standards` | rule.json R1 | AGENTS.md / `.ai` 规范引用 |

Fixture 位于 `scenarios/<id>/files/`，应用目标为 [`test_data/datacalc-web`](../../datacalc-web/)（GitLab `java_group/datacalc-web`）。

## rule.json 验证（D05 / D06）

datacalc-web 的 [`.opencodereview/rule.json`](../../datacalc-web/.opencodereview/rule.json) 定义两条 rule。D05/D06 通过 **双通道断言** 验证：

| 通道 | 数据源 | 验证内容 |
|------|--------|----------|
| Session trace | `~/.opencodereview/sessions/*/{job_id}/*.jsonl` | rule 是否注入 prompt；是否 `file_read` AGENTS.md / `.ai/*`；`code_comment` 是否含 severity 前缀 |
| MR publish | GitLab MR 评论 | OpenCodeReview 发帖与 severity 正则 |

**D05** 硬断言：R2 规则已注入 prompt（`must_rule_r2_injected`）。severity 前缀在 trace/MR 侧为 **warning**（`severity_warnings_only` / `regex_warnings_only`），因 LLM 未必严格遵守 `[HIGH]` 格式。

**D06** 硬断言：R1 已注入或 `file_read(AGENTS.md)`。`.ai` 未读、MR 关键词为 **warning**。

`rule.json` 在 D05/D06 fixture 中一并 push（合并为单条 rule，确保 OCR 注入 R1+R2 文案）。

环境变量（可选）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `OCR_SESSIONS_DIR` | `~/.opencodereview/sessions` | session JSONL 根目录 |
| `OCR_VIEWER_URL` | `http://localhost:5483` | 报告中的 Viewer 链接前缀 |

## 产物

报告写入仓库根 `test-results/ocr-e2e-<timestamp>-<scenario>/`：

- `ocr_e2e_report.zh.md` — 摘要
- `job_log.txt` — CI `code-review` 日志
- `gateway_job.json` — Gateway job 终态
- `assert.json` — OpenCodeReview MR 发帖断言
- `session_assert.json` — OCR session JSONL trace 断言（D05/D06）

## 模块说明

| 脚本 | 作用 |
|------|------|
| `run_e2e.py` / `run_e2e.ps1` | 主编排 |
| `apply_scenario.py` | 基线 `ocr-test-base` + 场景分支 push |
| `wait_for_review.py` | 等待 `code-review` job |
| `poll_gateway_job.py` | 轮询 `GET /v1/jobs/{id}` |
| `assert_ocr_publish.py` | MR 上 OpenCodeReview 断言 |
| `assert_ocr_session.py` | OCR session JSONL trace 断言（rule 注入 / 读文件 / severity） |
| `lib/ocr_session.py` | 解析 `~/.opencodereview/sessions` JSONL |
| `collect_report.py` | 跑后报告 |

## 重复执行

**可以重复执行。** 每次运行会：

1. 从 `ocr-test-base` 重建场景分支并 **force push**（产生新 commit）
2. 复用或创建对应 MR，触发新的 `code-review` Pipeline
3. 仅断言 **本轮**（`assert_since` 之后）的 OpenCodeReview 评论

若 fixture 与分支内容完全一致、无法产生新 commit，`apply_scenario` 会 **失败退出**（避免假通过）。

| 命令 | 重复跑的效果 |
|------|----------------|
| `-Scenario D01` | 同场景 MR 上新增一轮 Pipeline + 新评论；历史评论不影响断言 |
| `-All` | 顺序跑 D01→D06；D04 可与本轮 D02 的 inline 数对比 |
| 连续两次 `-All` | 均可通过（每次新 commit）；MR 评论会累积，报告目录按时间戳区分 |


- [ocr-ci2/docs/测试与验收.md](../../../ocr-ci2/docs/测试与验收.md)
- [test_data/README.md](../../README.md)

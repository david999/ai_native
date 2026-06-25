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
.\run_e2e.ps1 -Scenario D01_feature_date_guard
.\run_e2e.ps1 -All
.\run_e2e.ps1 -All -SkipPreflight
```

## 场景

| ID | 类型 | 说明 |
|----|------|------|
| `D01_feature_date_guard` | 功能开发 | 换电起止时间顺序校验 |
| `D02_bug_npe_optional` | Bug 引入 | `Optional.orElse(null)` 未校验 |
| `D03_bug_empty_catch` | Bug 引入 | 空 `catch` 吞异常 |
| `D04_bugfix_npe_guard` | Bug 修复 | 补 null guard |

Fixture 位于 `scenarios/<id>/files/`，应用目标为 [`test_data/datacalc-web`](../../datacalc-web/)（GitLab `java_group/datacalc-web`）。

## 产物

报告写入仓库根 `test-results/ocr-e2e-<timestamp>-<scenario>/`：

- `ocr_e2e_report.zh.md` — 摘要
- `job_log.txt` — CI `code-review` 日志
- `gateway_job.json` — Gateway job 终态
- `assert.json` — OpenCodeReview 发帖断言

## 模块说明

| 脚本 | 作用 |
|------|------|
| `run_e2e.py` / `run_e2e.ps1` | 主编排 |
| `apply_scenario.py` | 基线 `ocr-test-base` + 场景分支 push |
| `wait_for_review.py` | 等待 `code-review` job |
| `poll_gateway_job.py` | 轮询 `GET /v1/jobs/{id}` |
| `assert_ocr_publish.py` | MR 上 OpenCodeReview 断言 |
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
| `-All` | 顺序跑 D01→D04；D04 可与本轮 D02 的 inline 数对比 |
| 连续两次 `-All` | 均可通过（每次新 commit）；MR 评论会累积，报告目录按时间戳区分 |


- [ocr-ci2/docs/测试与验收.md](../../../ocr-ci2/docs/测试与验收.md)
- [test_data/README.md](../../README.md)

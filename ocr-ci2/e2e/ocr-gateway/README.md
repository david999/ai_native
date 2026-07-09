# OCR Gateway + datacalc-web 本地 E2E 自动化

在 **ocr-ci2 独立仓**内一键跑通：场景注入 → push → MR → GitLab CI `code-review` → OCR Gateway → MR 评论。

> monorepo 内旧路径 `test_data/e2e/ocr-gateway/` 为过渡期只读副本，**请在本目录维护**。

## 前置条件

1. 本地 GitLab（`:8000`）、Runner、OCR Gateway（`:8010`）已启动（GitLab 安装可参考 monorepo `evn/gitlab` 或公司标准 compose）
2. `git submodule update --init` 拉取 `e2e/fixtures/datacalc-web`
3. `~/.opencodereview/config.json` 含有效 LLM 与 `gitlab.api_token`
4. GitLab 已配置 `OCR_GATEWAY_SECRET`（至少一条 **非 Protected**）
5. 环境变量或 `ocr-ci2/.env` / `OCR_CI2_ENV_FILE` 含 `AICR_BOT_TOKEN` / `ROOT_PAT`

跑前检查（`run_e2e.py` 自动调用，默认跳过 AICR `:8001`）：

```powershell
cd ocr-ci2
.\scripts\acceptance\verify_gateway_runner.ps1 -ProjectPath java_group/datacalc-web -OcrGatewayOnly
```

## 快速开始

```powershell
cd ocr-ci2/e2e/ocr-gateway
pip install -r requirements-dev.txt

# 单元测试（不依赖 GitLab/Gateway/LLM）
python -m pytest -q

# 全链路 E2E（需 GitLab :8000 + Runner + Gateway :8010 + LLM）
.\run_e2e.ps1 -Scenario D01_feature_date_guard
.\run_e2e.ps1 -All
.\run_e2e.ps1 -All -SkipPreflight
```

## 样例仓 datacalc-web

默认路径：`ocr-ci2/e2e/fixtures/datacalc-web`（git submodule）。

```powershell
cd ocr-ci2
git submodule update --init e2e/fixtures/datacalc-web
```

Remote 为 `https://gitlab.aulton.com/java_group/datacalc-web.git`；本地 `:8000` GitLab 见 [e2e/README.md](../README.md) 的 `git insteadOf` 说明。

覆盖路径：`$env:OCR_E2E_DATACALC_DIR = "D:\path\to\datacalc-web"`

## 单元测试（pytest）

在 **`ocr-ci2/e2e/ocr-gateway`** 目录执行：

```powershell
python -m pytest -q
```

| 项 | 说明 |
|----|------|
| **测什么** | `tests/test_e2e_helpers.py`：manifest、MR 评论、Gateway job_id、JSONL session、`assert_ocr_*` |
| **不测什么** | 不 push、不调 GitLab/Gateway/LLM |
| **依赖** | `pip install -r requirements-dev.txt` |

## 场景

| ID | 类型 | 说明 |
|----|------|------|
| `D01_feature_date_guard` | 功能开发 | 换电起止时间顺序校验 |
| `D02_bug_npe_optional` | Bug 引入 | `Optional.orElse(null)` 未校验 |
| `D03_bug_empty_catch` | Bug 引入 | 空 `catch` 吞异常 |
| `D04_bugfix_npe_guard` | Bug 修复 | 补 null guard |
| `D05_rule_severity_prefix` | rule.json R2 | 严重级别前缀 |
| `D06_rule_ai_standards` | rule.json R1 | AGENTS.md / `.ai` 规范引用 |

Fixture 位于 `scenarios/<id>/files/`，应用目标为 [`e2e/fixtures/datacalc-web`](../fixtures/datacalc-web/)（GitLab `java_group/datacalc-web`）。

## 环境变量（可选）

| 变量 | 默认 | 说明 |
|------|------|------|
| `OCR_E2E_DATACALC_DIR` | `e2e/fixtures/datacalc-web` | 样例 Java 仓路径 |
| `OCR_E2E_RESULTS_DIR` | `ocr-ci2/test-results` | E2E 报告根目录 |
| `OCR_CI2_ENV_FILE` | — | 显式 `.env` 路径 |
| `OCR_SESSIONS_DIR` | `~/.opencodereview/sessions` | session JSONL 根 |
| `OCR_VIEWER_URL` | `http://localhost:5483` | Viewer 链接前缀 |
| `SEVERITY_DASHBOARD_URL` | `http://localhost:8010` | Dashboard 链接前缀 |

## 产物

报告写入 `ocr-ci2/test-results/ocr-e2e-<timestamp>-<scenario>/`：

- `ocr_e2e_report.zh.md` — 摘要
- `job_log.txt` — CI `code-review` 日志
- `gateway_job.json` — Gateway job 终态
- `assert.json` — MR 发帖断言
- `session_assert.json` — session JSONL 断言（D05/D06）

## 模块说明

| 脚本 | 作用 |
|------|------|
| `run_e2e.py` / `run_e2e.ps1` | 主编排 |
| `apply_scenario.py` | 基线 `ocr-test-base` + 场景分支 push |
| `lib/paths.py` | ocr-ci2 根、datacalc-web、报告路径 |
| `wait_for_review.py` | 等待 `code-review` job |
| `poll_gateway_job.py` | 轮询 `GET /v1/jobs/{id}` |
| `assert_ocr_publish.py` / `assert_ocr_session.py` | MR / session 断言 |
| `collect_report.py` | 跑后报告 |

## 相关文档

- [e2e/README.md](../README.md)
- [docs/测试与验收.md](../../docs/测试与验收.md)
- [docs/独立仓库迁移检查清单.md](../../docs/独立仓库迁移检查清单.md)

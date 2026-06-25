# Demo / 联调工程（test_data）

本目录用于 **独立的 Git 业务仓库**与**固定验收场景**，与 monorepo 分离版本管理。

## 布局

```
test_data/
├── datacalc-web/               # OCR Gateway 联调样例（Java，含 .gitlab-ci.yml）
├── e2e/ocr-gateway/            # OCR Gateway 自动化 E2E（6 场景，含 rule.json D05/D06）
├── spring-cloud-demo/          # AICR Reviewer 等业务仓（自有 .git）
├── fixtures/scenarios/         # 固定测试场景（纳入 monorepo）
│   ├── manifest.yaml
│   └── ...
└── scripts/                    # 场景应用、MR、校验、L3b 跑前检查
    ├── verify_l3b_runner.ps1
    └── ...
```

## OCR Gateway（ocr-ci2）联调

| 项 | 说明 |
|----|------|
| 样例仓 | [`datacalc-web/`](datacalc-web/) — 对应 GitLab `java_group/datacalc-web` |
| Gateway | `ocr-ci2/deploy/local/run.ps1`，`:8010` |
| CI 片段 | 与 [`ocr-ci2/deploy/prod/ci/snippet.native-host.yml`](../ocr-ci2/deploy/prod/ci/snippet.native-host.yml) 对齐 |
| 文档 | [ocr-ci2/docs/测试与验收.md](../ocr-ci2/docs/测试与验收.md) |
| 跑前检查 | `test_data/scripts/verify_l3b_runner.ps1 -ProjectPath java_group/datacalc-web` |
| **自动化 E2E** | [`e2e/ocr-gateway/run_e2e.ps1`](e2e/ocr-gateway/run_e2e.ps1) — D01–D06 全链路（D05/D06 验证 `.opencodereview/rule.json`） |

与 **AICR Reviewer（:8001）**、`spring-cloud-demo` 验收相互独立；勿混淆端口与 CI 变量。

## 获取 Demo

```bash
cd test_data
git clone http://localhost:8000/java_group/spring-cloud-demo.git
```

需先启动本地 GitLab（见 [`evn/gitlab/`](../evn/gitlab/)）。

## 固定测试场景

场景定义在 `fixtures/scenarios/`。详见 [docs/测试与验收.md](../docs/测试与验收.md)（AICR L1–L3）。

## CI 集成（AICR Reviewer）

业务仓库 `.gitlab-ci.yml` 引用：

- [`aicr-reviewer/ci/gitlab-ci.snippet.yml`](../aicr-reviewer/ci/gitlab-ci.snippet.yml)
- [docs/CI评审流水线.md](../docs/CI评审流水线.md)

| CI 变量 | 值 |
|---------|-----|
| `AICR_REVIEW_URL` | `http://host.docker.internal:8001` |
| `AICR_REVIEW_SECRET` | 与 `evn/.env` 中 `REVIEW_API_SECRET` 一致 |

## 全链路验收

- AICR 分层：[docs/测试与验收.md](../docs/测试与验收.md)
- OCR Gateway L3b 跑前：`test_data/scripts/verify_l3b_runner.ps1`
- **OCR Gateway 自动化 E2E**：`test_data/e2e/ocr-gateway/run_e2e.ps1 -All`（报告含 `session_assert.json` + Viewer 链接）


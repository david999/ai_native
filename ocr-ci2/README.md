# OCR Gateway（ocr-ci2）

**OCR 部署一次、Gateway 常驻**；每个 MR 的 GitLab CI Job 仅 **HTTP 触发** Gateway，由 Gateway 执行 `ocr review` 并回写 MR 评论。

**项目汇报总结**（概念、选型、架构、亮点）：[docs/项目汇报总结.md](docs/项目汇报总结.md)  
架构见 [docs/架构说明.md](docs/架构说明.md)。  
**联调与 E2E 验收**（含 monorepo 样例仓）见 [docs/测试与验收.md](docs/测试与验收.md)。

## 架构

```text
MR Pipeline
  └─ code-review Job（curl 镜像，秒级启动）
        POST /v1/review/merge-request
              ↓
     OCR Gateway（:8010，原生或 Docker）
        workspace 缓存 fetch → ocr review → post_ocr_to_gitlab.py
              ↓
     GitLab MR 行内评论
     Dashboard（同 :8010 `/`）← review-index + session JSONL
       ├─ 方案 C（默认）：Vue 3 SPA（`OCR_DASHBOARD_SPA=1`；设 `0` 回退 HTMX `/legacy`）
       ├─ 方案 A（可选）：HTMX 评审工作台（`OCR_DASHBOARD_SPA=0` 或 SPA dist 缺失时）
       └─ JSON API `/api/reviews`、`/api/reviews/{job_id}`、`/api/stats`、`/api/repos`…
       （可选官方 OCR Viewer 链接默认隐藏，设 `OCR_VIEWER_ENABLED=1` 恢复）
```

## 快速开始（本地，仅原生）

```powershell
# 1. ~/.opencodereview/config.json（llm + gitlab.api_token）
# 2. 安装并启动 Gateway（无需 Docker）
cd ocr-ci2
.\deploy\local\install.ps1   # ocr 已安装则跳过 npm install -g
Copy-Item deploy\local\gateway.env.example deploy\local\gateway.env
.\deploy\local\run.ps1
curl http://localhost:8010/health
# Dashboard: http://localhost:8010/  （默认方案 C SPA；需先 npm run build）
# 统计概览: http://localhost:8010/stats
# 回退方案 A：gateway.env 设 OCR_DASHBOARD_SPA=0，或访问 /legacy/
# SPA 构建：cd viewer-spa; npm install; npm run build
# 可选官方 Viewer（默认关闭）：设 OCR_VIEWER_ENABLED=1 后 ocr viewer → http://localhost:5483

# 3. 业务仓 CI：复制 deploy/prod/ci/snippet.native-host.yml → 业务仓库 .gitlab-ci.yml
# GitLab Variables: OCR_GATEWAY_SECRET=local-dev-secret
```

完整步骤见 [docs/本地部署指南.md](docs/本地部署指南.md)。

## 生产部署

**Docker**（推荐）：单镜像含 OCR CLI + Gateway。  
- **逐步操作**：[docs/生产环境部署操作指南.md](docs/生产环境部署操作指南.md)  
- **概念与网络**：[docs/生产部署指南.md](docs/生产部署指南.md)

## 文件说明

### `gateway/` — HTTP 服务

| 文件 | 作用 |
|------|------|
| [main.py](gateway/main.py) | FastAPI：API（`/health`、`/v1/*`）+ Dashboard UI（`/`、`/repos`、`/mr/*`、`/r/*`） |
| [review_service.py](gateway/review_service.py) | git fetch、`ocr review`、发帖、可选 MR note |
| [workspace_cache.py](gateway/workspace_cache.py) | bare mirror + worktree 缓存 |
| [config.py](gateway/config.py) | 环境变量与默认路径 |
| [requirements.txt](gateway/requirements.txt) | Python 依赖 |

### `scripts/` — 运行时脚本

| 文件 | 作用 |
|------|------|
| [post_ocr_to_gitlab.py](scripts/post_ocr_to_gitlab.py) | OCR JSON → GitLab MR 评论 |
| [gitlab_mr.py](scripts/gitlab_mr.py) | GitLab MR API 工具（含 `[HIGH]`/`[MEDIUM]`/`[LOW]` 着色） |
| [session_telemetry.py](scripts/session_telemetry.py) | 扫描 JSONL severity / token 统计 |
| [review_index.py](scripts/review_index.py) | Gateway MR 评审索引（`review-index.jsonl`） |
| [seed_dashboard_demo.py](scripts/seed_dashboard_demo.py) | 从本地 Session 生成演示 MR 索引（工作台/统计联调） |
| [session_job_link.py](scripts/session_job_link.py) | job_id → session JSONL 关联 |
| [ocr_ci_config.py](scripts/ocr_ci_config.py) | 读取 `config.json` / 环境变量 |

### `viewer/` — Dashboard UI（并入 Gateway :8010）

| 文件 | 作用 |
|------|------|
| [routes.py](viewer/routes.py) | HTML 路由 + `OCR_DASHBOARD_SPA` 切换（SPA 时 HTMX 挂 `/legacy`） |
| [api.py](viewer/api.py) | JSON API：reviews / stats / repos / session / mr history |
| [basicauth.py](viewer/basicauth.py) | 可选 Basic Auth（设 `OCR_DASHBOARD_USER`/`OCR_DASHBOARD_PASSWORD` 启用） |
| [static/app.js](viewer/static/app.js) | 方案 A 工作台 master-detail + 运行中 job 自动刷新 |
| [static/stats.js](viewer/static/stats.js) | 方案 A 统计概览 Chart.js（CDN 失败降级） |
| [templates/](viewer/templates/) | 方案 A Jinja2 模板 |
| [app.py](viewer/app.py) | 已废弃独立 :5484 启动；请用 `deploy/local/run.ps1` |

### `viewer-spa/` — 方案 C Vue 3 SPA（可选）

| 文件 | 作用 |
|------|------|
| [package.json](viewer-spa/package.json) | Vue 3 + Vite + vue-router |
| [src/views/WorkbenchView.vue](viewer-spa/src/views/WorkbenchView.vue) | 三栏：MR → issues → 详情（可跳 GitLab） |
| [src/views/StatsView.vue](viewer-spa/src/views/StatsView.vue) | 统计概览（纯 CSS 柱状图） |
| [dist/](viewer-spa/dist/) | `npm run build` 产物；Gateway `StaticFiles(html=True)` 托管 |

启用：默认 `OCR_DASHBOARD_SPA=1`（需已构建 `viewer-spa/dist`；缺失则自动回退 HTMX）。关闭：`OCR_DASHBOARD_SPA=0`。开发：`cd viewer-spa && npm run dev`（代理 `/api` → `:8010`）。

数据源仍是 `review-index.jsonl` + session JSONL（无 DB）；下迭代可替换 `load_all_records()`/`load_session()` 实现，API 契约不变。
与官方 `ocr viewer`（:5483）读同一 JSONL；官方 viewer 跳转链接默认隐藏（`OCR_VIEWER_ENABLED=0`），开启后自动恢复。

### `config/` — 配置模板

| 文件 | 作用 |
|------|------|
| [ocr-gateway.config.json.example](config/ocr-gateway.config.json.example) | Gateway / 生产 bake 示例 |
| [ocr-ci.config.json.example](config/ocr-ci.config.json.example) | 通用 OpenCodeReview 配置示例 |

### `deploy/` — 部署脚本

见 [deploy/README.md](deploy/README.md)。

| 目录 | 作用 |
|------|------|
| [deploy/local/](deploy/local/) | Windows 本地原生 |
| [deploy/prod/native/](deploy/prod/native/) | Linux 生产原生 |
| [deploy/prod/docker/](deploy/prod/docker/) | 生产 Docker |
| [deploy/prod/ci/](deploy/prod/ci/) | GitLab CI snippet |

### `docs/` — 文档

见 [docs/文档索引.md](docs/文档索引.md)。

### `tests/` — 测试

| 文件 | 作用 |
|------|------|
| test_gateway_api.py 等 | 单元测试（默认 `pytest`） |
| [test_dashboard_spa.py](tests/test_dashboard_spa.py) | 方案 C SPA 开关与 API `issues`/repos smoke |
| `e2e/ocr-gateway/tests/` | E2E 辅助逻辑 pytest（见 [e2e/ocr-gateway/README.md](e2e/ocr-gateway/README.md)） |

## 配置

- 本地原生：`~/.opencodereview/config.json`（改完重启 Gateway）
- 生产 Docker：`build_image.ps1` bake 进镜像

Gateway 环境变量见 [docs/本地部署指南.md](docs/本地部署指南.md)、[docs/生产部署指南.md](docs/生产部署指南.md)。

## 测试

```powershell
cd ocr-ci2
pip install -r requirements-dev.txt
pytest                              # 单元测试（tests/）
cd e2e/ocr-gateway; python -m pytest -q   # E2E 辅助用例
```

E2E 见 [docs/测试与验收.md](docs/测试与验收.md)。

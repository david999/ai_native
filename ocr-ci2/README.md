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
# Dashboard: http://localhost:8010/  （MR 评审流）
# 可选官方 Viewer: ocr viewer  → http://localhost:5483

# 3. 业务仓 CI：复制 deploy/prod/ci/snippet.native-host.yml → 业务仓库 .gitlab-ci.yml
# GitLab Variables: OCR_GATEWAY_SECRET=local-dev-secret
```

完整步骤见 [docs/本地部署指南.md](docs/本地部署指南.md)。

## 生产部署

默认 **Linux 原生**（systemd）；可选 **Docker**。完整步骤（GitLab 账号/Runner/OCR/Gateway/试点项目/域名说明）见 [docs/生产部署指南.md](docs/生产部署指南.md) 与 [deploy/README.md](deploy/README.md)。

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
| [session_job_link.py](scripts/session_job_link.py) | job_id → session JSONL 关联 |
| [ocr_ci_config.py](scripts/ocr_ci_config.py) | 读取 `config.json` / 环境变量 |

### `viewer/` — Dashboard UI（并入 Gateway :8010）

| 文件 | 作用 |
|------|------|
| [routes.py](viewer/routes.py) | MR 评审流首页、repo/session 页、模板 |
| [app.py](viewer/app.py) | 已废弃独立 :5484 启动；请用 `deploy/local/run.ps1` |

与官方 `ocr viewer`（:5483）读同一 JSONL；Dashboard 内保留跳转 :5483（FileTokenBreakdown）。

### `config/` — 配置模板

| 文件 | 作用 |
|------|------|
| [defaults.config.json](config/defaults.config.json) | OCR 默认片段 |
| [ocr-gateway.config.json.example](config/ocr-gateway.config.json.example) | Gateway 场景示例 |
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
| [test_gitlab_mr_sync.py](tests/test_gitlab_mr_sync.py) | **可选**：monorepo 内与 ocr-ci 脚本同步校验 |

## 配置

- 本地原生：`~/.opencodereview/config.json`（改完重启 Gateway）
- 生产 Docker：`build_image.ps1` bake 进镜像

Gateway 环境变量见 [docs/本地部署指南.md](docs/本地部署指南.md)、[docs/生产部署指南.md](docs/生产部署指南.md)。

## 测试

```powershell
cd ocr-ci2
pip install -r requirements-dev.txt
pytest
```

E2E 见 [docs/测试与验收.md](docs/测试与验收.md)。

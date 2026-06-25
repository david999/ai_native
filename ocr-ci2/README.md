# OCR Gateway（ocr-ci2）

**方案 3**：OCR **部署一次、Gateway 常驻**；每个 MR 的 GitLab CI Job 仅 **HTTP 触发** Gateway，由 Gateway 执行 `ocr review` 并回写 MR 评论。

与 [`ocr-ci/`](../ocr-ci/)（方案 2：每 Job 启动 `ocr-ci:local` 容器跑 OCR）并列，详见 [`docs/方案评估.md`](docs/方案评估.md)。

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
```

## 快速开始（本地，仅原生）

```powershell
# 1. ~/.opencodereview/config.json（llm + gitlab.api_token）
# 2. 安装并启动 Gateway（无需 Docker）
cd E:\ai_native\ocr-ci2
.\deploy\local\install.ps1   # ocr 已安装则跳过 npm install -g
Copy-Item deploy\local\gateway.env.example deploy\local\gateway.env
.\deploy\local\run.ps1
curl http://localhost:8010/health

# 3. 业务仓 CI（Gateway 在宿主机）
Copy-Item deploy\prod\ci\snippet.native-host.yml E:\ai_native\test_data\spring-cloud-demo\.gitlab-ci.yml
# GitLab Variables: OCR_GATEWAY_SECRET=local-dev-secret
```

完整步骤见 [`docs/本地部署指南.md`](docs/本地部署指南.md)。

## 生产部署

默认 **Linux 原生**（systemd）；可选 **Docker**。见 [`docs/生产部署指南.md`](docs/生产部署指南.md) 与 [`deploy/README.md`](deploy/README.md)。

## 文件说明

### `gateway/` — HTTP 服务（共享，与部署方式无关）

| 文件 | 作用 |
|------|------|
| [`main.py`](gateway/main.py) | FastAPI 入口：`/health`、`POST /v1/review/merge-request`、`GET /v1/jobs/{id}`；鉴权与异步入队 |
| [`review_service.py`](gateway/review_service.py) | 评审编排：git fetch/checkout、`ocr review` 子进程、调用发帖脚本、可选 MR 进度 note |
| [`workspace_cache.py`](gateway/workspace_cache.py) | 按 `project_id` 缓存 bare mirror，LRU 淘汰与磁盘复用 |
| [`config.py`](gateway/config.py) | 从环境变量读取 Gateway 配置（SECRET、GitLab URL、WORK_ROOT、POST_SCRIPT 等） |
| [`requirements.txt`](gateway/requirements.txt) | Gateway Python 依赖（FastAPI、uvicorn 等） |

### `scripts/` — 运行时脚本（共享）

| 文件 | 作用 |
|------|------|
| [`post_ocr_to_gitlab.py`](scripts/post_ocr_to_gitlab.py) | 解析 OCR stdout JSON，调用 GitLab API 写 MR 行内评论 |
| [`gitlab_mr.py`](scripts/gitlab_mr.py) | GitLab MR 评论/Note 的共享工具（与 `ocr-ci` 同源逻辑） |
| [`ocr_ci_config.py`](scripts/ocr_ci_config.py) | 读取/合并 OCR 配置（`config.json`、环境变量） |
| [`acceptance/bake_ocr_config.py`](scripts/acceptance/bake_ocr_config.py) | 将 `~/.opencodereview/config.json` bake 为 `.build/config.json`（Docker 构建用） |

### `config/` — 配置模板（非密钥）

| 文件 | 作用 |
|------|------|
| [`defaults.config.json`](config/defaults.config.json) | OCR 默认配置片段 |
| [`ocr-gateway.config.json.example`](config/ocr-gateway.config.json.example) | Gateway 场景下的 OCR 配置示例 |
| [`ocr-ci.config.json.example`](config/ocr-ci.config.json.example) | 与 ocr-ci 对齐的配置示例 |

### `deploy/` — 部署脚本（按环境拆分）

部署各文件逐项说明见 [`deploy/README.md`](deploy/README.md)。脚本与 Python 模块文件头含 **逻辑清单** 注释（校验 / 跳过 / 不做），便于对照是否包含某项逻辑。

| 目录 | 作用 |
|------|------|
| [`deploy/local/`](deploy/local/) | **本地 Windows**：原生 install / run / `gateway.env` |
| [`deploy/prod/native/`](deploy/prod/native/) | **生产默认**：Linux install / run / systemd / env |
| [`deploy/prod/docker/`](deploy/prod/docker/) | **生产可选**：Dockerfile、compose、镜像构建与启动 |
| [`deploy/prod/ci/`](deploy/prod/ci/) | GitLab CI snippet（宿主机 Gateway / Docker Gateway） |

### `docs/` — 文档

| 文件 | 作用 |
|------|------|
| [`本地部署指南.md`](docs/本地部署指南.md) | Windows 本地原生部署（Gateway 在宿主机） |
| [`生产部署指南.md`](docs/生产部署指南.md) | 生产：Linux 原生（默认）+ Docker（可选） |
| [`方案评估.md`](docs/方案评估.md) | ocr-ci vs ocr-ci2 vs Webhook 选型与架构说明 |

### `tests/` — 单元测试

| 文件 | 作用 |
|------|------|
| [`test_gateway_api.py`](tests/test_gateway_api.py) | HTTP API：鉴权、入队、job 查询 |
| [`test_review_service.py`](tests/test_review_service.py) | 评审编排逻辑 |
| [`test_workspace_cache.py`](tests/test_workspace_cache.py) | mirror 缓存与 LRU |
| [`test_gitlab_mr.py`](tests/test_gitlab_mr.py) | MR 评论工具 |
| [`test_gitlab_mr_sync.py`](tests/test_gitlab_mr_sync.py) | 与 ocr-ci `gitlab_mr.py` 行为一致性 |
| [`test_config_defaults.py`](tests/test_config_defaults.py) | 默认路径与环境变量 |
| [`test_deploy_layout.py`](tests/test_deploy_layout.py) | `deploy/` 关键文件存在性 |

### 仓库根目录

| 文件 | 作用 |
|------|------|
| [`.dockerignore`](.dockerignore) | `docker build` 时排除无关文件（context 为仓库根） |
| [`.gitignore`](.gitignore) | 忽略 `.build/`、`.gateway-work/`、各 `gateway.env` |
| [`gitlab-ci.ocr-gateway.snippet.native-host.yml`](gitlab-ci.ocr-gateway.snippet.native-host.yml) | **已迁移 stub**，实际内容在 `deploy/prod/ci/snippet.native-host.yml` |
| [`gitlab-ci.ocr-gateway.snippet.yml`](gitlab-ci.ocr-gateway.snippet.yml) | **已迁移 stub**，实际内容在 `deploy/prod/ci/snippet.docker.yml` |
| [`requirements-dev.txt`](requirements-dev.txt) | 开发与 pytest 依赖 |

## 配置

本地原生：**`~/.opencodereview/config.json`**（改完即生效，无需 bake）。

生产 Docker：同上文件经 `deploy/prod/docker/build_image.ps1` bake 进镜像。

Gateway 环境变量见 [`docs/本地部署指南.md`](docs/本地部署指南.md) 与 [`docs/生产部署指南.md`](docs/生产部署指南.md)。

## 测试

```powershell
cd E:\ai_native\ocr-ci2
pip install -r requirements-dev.txt
pytest
```

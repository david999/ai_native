# ocr-ci2 部署目录说明

部署脚本与业务代码分离：`gateway/`、`scripts/` 为共享运行时；本目录仅含 **安装、启动、环境模板与 CI 片段**。

## 选型

| 路径 | 适用场景 | 方式 |
|------|----------|------|
| [`local/`](local/) | **本地开发**（Windows） | 仅原生 — Gateway 跑在宿主机 |
| [`prod/native/`](prod/native/) | **生产**（默认） | Linux 原生 + systemd |
| [`prod/docker/`](prod/docker/) | **生产**（可选） | Docker 镜像 + compose |
| [`prod/ci/`](prod/ci/) | 业务仓 GitLab CI | 轻量 curl Job 触发 Gateway |

文档：本地见 [`../docs/本地部署指南.md`](../docs/本地部署指南.md)；生产见 [`../docs/生产部署指南.md`](../docs/生产部署指南.md)。

---

## `local/` — 本地 Windows（原生）

| 文件 | 作用 |
|------|------|
| [`install.ps1`](local/install.ps1) | 检查 node/npm/python/git；`ocr version` 成功则跳过 npm install -g；始终 pip install Gateway 依赖 |
| [`run.ps1`](local/run.ps1) | 加载 `gateway.env`，启动 `uvicorn gateway.main:app`（默认 `:8010`） |
| [`gateway.env.example`](local/gateway.env.example) | 本地 env 模板：`OCR_GATEWAY_GITLAB_*` → GitLab **:8000**；Gateway 监听 **:8010**（`OCR_GATEWAY_PORT`）；CI 用 `OCR_GATEWAY_URL` → **:8010** |

使用：复制 `gateway.env.example` → `gateway.env`（已 gitignore），再执行 `run.ps1`。

---

## `prod/native/` — 生产 Linux（默认）

| 文件 | 作用 |
|------|------|
| [`install.sh`](prod/native/install.sh) | 同 local：`ocr version` 成功则跳过 npm（`SKIP_OCR_NPM=1` 可整段跳过）；始终 pip install |
| [`run.sh`](prod/native/run.sh) | 加载 `gateway.env`，前台启动 Gateway |
| [`gateway.env.example`](prod/native/gateway.env.example) | 生产 env 模板（建议 `OCR_GATEWAY_WORK_ROOT=/var/ocr-gateway/work`） |
| [`ocr-gateway.service.example`](prod/native/ocr-gateway.service.example) | systemd unit 示例；`EnvironmentFile` 指向 `deploy/prod/native/gateway.env` |

配置 OCR：宿主机 `~/.opencodereview/config.json`，改完重启服务即可，无需 rebuild。

---

## `prod/docker/` — 生产 Docker（可选）

| 文件 | 作用 |
|------|------|
| [`Dockerfile`](prod/docker/Dockerfile) | OCR 运行时 + Gateway 合一镜像；COPY `gateway/`、`scripts/`、`.build/config.json` |
| [`docker-compose.yml`](prod/docker/docker-compose.yml) | 常驻容器 `:8010`；与 GitLab 同 `gitlab_default` 网络时使用 `http://gitlab:8000` |
| [`.dockerignore`](prod/docker/.dockerignore) | docker 目录侧参考；实际 build 使用仓库根 [`.dockerignore`](../.dockerignore) |
| [`build_image.ps1`](prod/docker/build_image.ps1) | 在 **ocr-ci2 根目录** bake 配置并 `docker build -f deploy/prod/docker/Dockerfile .` |
| [`run.ps1`](prod/docker/run.ps1) | `docker compose -f deploy/prod/docker/docker-compose.yml up` |
| [`gateway.env.example`](prod/docker/gateway.env.example) | compose 环境变量说明（`OCR_GATEWAY_GITLAB_URL=http://gitlab:8000` 等） |

改 OCR 配置后需重新 `build_image.ps1` 并 recreate 容器。

---

## `prod/ci/` — GitLab CI 片段

复制到业务仓库 `.gitlab-ci.yml` 或 `include` 使用。

| 文件 | 作用 |
|------|------|
| [`snippet.native-host.yml`](prod/ci/snippet.native-host.yml) | Gateway 在**宿主机**：`OCR_GATEWAY_URL=http://host.docker.internal:8010`（Runner 在 Docker 内） |
| [`snippet.docker.yml`](prod/ci/snippet.docker.yml) | Gateway 在**容器**：`OCR_GATEWAY_URL=http://ocr-gateway:8010`（与 GitLab 同 Docker 网） |

两片段均使用 `curlimages/curl` 轻量镜像 `POST /v1/review/merge-request`；需在 GitLab CI Variables 配置 `OCR_GATEWAY_SECRET`（与对应 `gateway.env` 一致）。

---

## 共享运行时（不在本目录）

| 路径 | 作用 |
|------|------|
| [`../gateway/`](../gateway/) | FastAPI Gateway 服务代码 |
| [`../scripts/post_ocr_to_gitlab.py`](../scripts/post_ocr_to_gitlab.py) | OCR 结果发帖 |
| [`../scripts/gitlab_mr.py`](../scripts/gitlab_mr.py) | GitLab MR API 工具 |

# ocr-ci2 部署目录说明

部署脚本与业务代码分离：`gateway/`、`scripts/` 为共享运行时；本目录仅含 **安装、启动、环境模板与 CI 片段**。

文档：本地见 [docs/本地部署指南.md](../docs/本地部署指南.md)；生产逐步操作见 [docs/生产环境部署操作指南.md](../docs/生产环境部署操作指南.md)。

## 选型

| 路径 | 适用场景 | 方式 |
|------|----------|------|
| [local/](local/) | **本地开发**（Windows） | 仅原生 — Gateway 跑在宿主机 |
| [prod/docker/](prod/docker/) | **生产**（推荐） | Docker 镜像 + compose（OCR 打入 Gateway 镜像） |
| [prod/native/](prod/native/) | **生产**（备选） | Linux 原生 + systemd |
| [prod/ci/](prod/ci/) | 业务仓 GitLab CI | 轻量 curl Job 触发 Gateway |

---

## `local/` — 本地 Windows（原生）

| 文件 | 作用 |
|------|------|
| [install.ps1](local/install.ps1) | 检查 node/npm/python/git/ocr；pip install Gateway 依赖 |
| [run.ps1](local/run.ps1) | 加载 `gateway.env`，启动 uvicorn `:8010`（API + Dashboard） |
| [run_viewer.ps1](local/run_viewer.ps1) | **已废弃** — 转发到 `run.ps1` |
| [gateway.env.example](local/gateway.env.example) | 本地 env 模板（含 Dashboard / `OCR_VIEWER_URL`） |

使用：复制 `gateway.env.example` → `gateway.env`，再执行 `run.ps1`。

---

## `prod/native/` — 生产 Linux（默认）

| 文件 | 作用 |
|------|------|
| [install.sh](prod/native/install.sh) | 同 local 逻辑 |
| [run.sh](prod/native/run.sh) | 前台启动 Gateway |
| [gateway.env.example](prod/native/gateway.env.example) | 生产 env 模板 |
| [ocr-gateway.service.example](prod/native/ocr-gateway.service.example) | systemd unit |

配置 OCR：宿主机 `~/.opencodereview/config.json`，改完重启服务即可。

---

## `prod/docker/` — 生产 Docker（推荐）

| 文件 | 作用 |
|------|------|
| [Dockerfile](prod/docker/Dockerfile) | OCR + Gateway 合一镜像 |
| [docker-compose.yml](prod/docker/docker-compose.yml) | 与 GitLab 同 Docker 网络（`gitlab_default`） |
| [docker-compose.standalone.yml](prod/docker/docker-compose.standalone.yml) | GitLab 独立部署（Aulton：`48010:8010`） |
| [aulton.prod.env.example](prod/docker/aulton.prod.env.example) | Aulton 生产 IP/端口/CI URL（`172.16.5.119:48010`） |
| [prod.config.json.example](prod/docker/prod.config.json.example) | bake 用配置模板（复制为 `prod.config.json`，勿提交） |
| [build_image.ps1](prod/docker/build_image.ps1) | 在 **ocr-ci2 根目录** bake 并 build |
| [run.ps1](prod/docker/run.ps1) | compose up（默认 `docker-compose.yml`） |
| [gateway.env.example](prod/docker/gateway.env.example) | compose 环境变量说明 |

操作步骤见 [docs/生产环境部署操作指南.md](../docs/生产环境部署操作指南.md)。改 OCR 配置后需重新 `build_image.ps1` 并 recreate 容器。

---

## `prod/ci/` — GitLab CI 片段

| 文件 | 作用 |
|------|------|
| [snippet.native-host.yml](prod/ci/snippet.native-host.yml) | Gateway 在**宿主机**；URL 示例 `http://host.docker.internal:8010` |
| [snippet.docker.yml](prod/ci/snippet.docker.yml) | Gateway 在**容器**；URL 示例 `http://ocr-gateway:8010` |

须在 GitLab CI/CD Variables 配置 **`OCR_GATEWAY_URL`**、**`OCR_GATEWAY_SECRET`**（与对应 `gateway.env` / compose 一致；推荐群组或实例级注入，勿写进 snippet）。

---

## 共享运行时（不在本目录）

| 路径 | 作用 |
|------|------|
| [gateway/](../gateway/) | FastAPI Gateway |
| [scripts/post_ocr_to_gitlab.py](../scripts/post_ocr_to_gitlab.py) | OCR 结果发帖 |
| [scripts/gitlab_mr.py](../scripts/gitlab_mr.py) | GitLab MR API 工具 |

# 本地 GitLab CE（`evn/gitlab`）

本目录用于 **L3 全链路验收** 的 GitLab CE 实例。数据在 `data/`、`config/`、`logs/`（gitignore），与 [`docker-compose.yml`](docker-compose.yml) 卷挂载一致。

## 组件分工

| 组件 | 作用 | L3 是否必需 |
|------|------|-------------|
| **Rancher Desktop** | 提供 Linux 容器引擎（moby/docker CLI），替代 Docker Desktop | 是 |
| **GitLab CE 容器** | Web/API/Git，`:8000` | 是 |
| **`gitlab-runner-windows-amd64.exe`** | CI Job 执行器，注册到 GitLab | **否**（当前 L3 直接调 AICR `/review`） |

`gitlab-runner.exe` **不能**替代 GitLab 服务。

## 自动化启动（验收脚本）

```text
run_acceptance.ps1 -Level L3
  → test_data/scripts/ensure_gitlab.ps1
  → test_data/scripts/start_gitlab.ps1
       → test_data/scripts/ensure_rancher.ps1   # rdctl 后台启动 + 等 docker
       → evn/gitlab/start.ps1                   # docker compose up -d gitlab
```

无需手动打开 Rancher GUI；无需配置 `GITLAB_START_COMMAND`（除非要覆盖默认链路）。

## 手动验证

```powershell
cd E:\ai_native\test_data\scripts
.\ensure_rancher.ps1
cd E:\ai_native\evn\gitlab
.\start.ps1
# 浏览器 http://localhost:8000
```

## 可选环境变量

| 变量 | 默认 |
|------|------|
| `RANCHER_RDCTL` | `C:\Program Files\Rancher Desktop\resources\resources\win32\bin\rdctl.exe` |
| `RANCHER_DOCKER_BIN` | `%USERPROFILE%\.rd\bin` |
| `GITLAB_URL` | `http://localhost:8000` |
| `GITLAB_IMAGE_MIRROR` | `docker.m.daocloud.io/gitlab/gitlab-ce:latest`（Docker Hub 不可达时由 `start.ps1` 拉取并 tag） |

Rancher 建议：**Container Engine = dockerd (moby)**，**Kubernetes 可关闭**。

## 可选：Windows GitLab Runner（CI E2E）

L3 通过后，若需测「GitLab CI → curl /review」：

1. GitLab 已在 `:8000` 运行
2. GitLab UI → Settings → CI/CD → Runners → 获取 registration token
3. 注册：

```powershell
cd E:\ai_native\evn\gitlab
.\gitlab-runner-windows-amd64.exe register `
  --url http://localhost:8000 `
  --registration-token <token> `
  --executor shell `
  --description "windows-local"
```

4. 运行：`.\gitlab-runner-windows-amd64.exe run`

compose 内的 `gitlab-runner` **服务**默认不启动（避免与 Rancher 套娃）；优先用本机 exe。

## 与 Docker Desktop 的关系

- **禁止**：Docker Desktop（商业许可）
- **使用**：Rancher Desktop + 本目录现有 compose/数据卷
- **不重建**：项目、用户、PAT、`spring-cloud-demo` remote 通常可继续用

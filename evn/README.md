# 本地 / 部署环境（evn）

本目录存放 **环境变量**、**GitLab Docker 编排** 与 **AICR 部署配置模板**。运行时大数据与密钥不提交 Git（见根目录 [`.gitignore`](../.gitignore)）。

## 目录结构

```
evn/
├── .env.example          # 环境变量模板（可提交）
├── .env                  # 真实密钥（gitignore，从 example 复制）
├── .aicr/
│   └── config.toml.example   # 阶段 C 部署配置模板（可提交）
├── .aicr-state/          # 增量评审状态（gitignore，运行时生成）
├── gitlab/
│   ├── docker-compose.yml    # GitLab CE + Runner（可提交）
│   ├── data/                 # GitLab 数据（gitignore）
│   ├── logs/                 # 日志（gitignore）
│   └── config/               # gitlab-secrets 等（gitignore）
└── gitlab-runner/
    └── config/               # Runner config.toml（gitignore）
```

## 首次配置

```bash
# 仓库根目录
cp evn/.env.example evn/.env
# 编辑 evn/.env，见 docs/环境变量与密钥.md

# 可选：阶段 C 部署配置
cp evn/.aicr/config.toml.example evn/.aicr/config.toml
```

Windows PowerShell：

```powershell
Copy-Item evn\.env.example evn\.env
```

## 本地日常（推荐，不依赖 Docker Desktop）

```powershell
cd aicr-reviewer
.\scripts\run_local.ps1          # AICR → http://localhost:8001
.\scripts\run_acceptance.ps1 -Level daily   # L1+L2 中文报告
```

GitLab 通过 **Rancher Desktop** + [`gitlab/docker-compose.yml`](gitlab/docker-compose.yml) 启动（**非 Docker Desktop**）。**daily** 不碰 GitLab；**L3** 脚本自动 `ensure_rancher` → [`gitlab/start.ps1`](gitlab/start.ps1)。详见 [`gitlab/README.md`](gitlab/README.md)。

## 可选：GitLab + AICR（Docker，生产/实验）

以下仅在你**明确采用容器部署**时使用；与本地 `daily` 验收无关。

```bash
docker network create gitlab_default   # 若不存在
cd evn/gitlab
docker compose up -d
```

- Web：`http://localhost:8000`

## 可选：AICR Reviewer（Docker）

```bash
cd aicr-reviewer && docker build -t gitlab-aicr-reviewer:latest .

cd evn/gitlab
docker compose -f docker-compose.yml \
  -f ../../aicr-reviewer/deploy/docker-compose.aicr-reviewer.yml \
  up -d aicr-reviewer
```

Compose 通过 `env_file: ../../evn/.env` 注入变量；容器内 `GITLAB_URL=http://gitlab:8000`。

## 本地无 Docker

仅启动评审服务：

```powershell
cd aicr-reviewer
.\scripts\run_local.ps1
```

`.env` 中 `GITLAB_URL=http://localhost:8000`。

## 与 Git 的边界

| 可提交 | 勿提交 |
|--------|--------|
| `.env.example`、`config.toml.example`、`gitlab/docker-compose.yml` | `.env`、`config.toml`、`.aicr-state/` |
| | `gitlab/data/`、`gitlab/logs/`、`gitlab/config/` |
| | `gitlab-runner/config/` |

详见 [docs/环境变量与密钥.md](../docs/环境变量与密钥.md)。

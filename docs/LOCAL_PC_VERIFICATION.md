# 本地 PC 测试与整体验收指南

本文说明在**个人电脑**（Windows / Linux / macOS）上如何跑测试、启动服务，以及按层级**验收整个 AICR 工程**。自动化用例细节见 [TESTING.md](./TESTING.md)；密钥说明见 [SECRETS.md](./SECRETS.md)。

---

## 1. 环境准备

### 1.1 通用要求

| 项目 | 建议版本 | 用途 |
|------|----------|------|
| **Python** | 3.10+（推荐 3.12） | 评审服务、冒烟测试 |
| **Git** | 任意较新版本 | 克隆仓库、Demo MR |
| **curl** | 系统自带或单独安装 | 健康检查、手工调 `/review` |
| **jq** | 可选 | 本地模拟 `ci_review_gate.sh` 解析 JSON |

仓库根目录记为 `<repo>`（例如 `E:\ai_native` 或 `~/ai_native`）。

### 1.2 Windows

1. 安装 [Python 3](https://www.python.org/downloads/)，安装时勾选 **Add python.exe to PATH**。
2. 打开 **PowerShell** 或 **Windows Terminal**，进入仓库：
   ```powershell
   cd E:\ai_native
   ```
3. 若 `python -m venv` 报错，在「应用和功能」中确认已安装 **Python Launcher**；必要时用 `py -3.12 -m venv` 代替 `python -m venv`。
4. **curl**：Windows 10 1803+ 自带；也可在 PowerShell 中用 `Invoke-WebRequest`（下文给出等价示例）。

### 1.3 Linux / macOS

```bash
cd ~/ai_native   # 按实际路径调整
```

Ubuntu/Debian 若 `python3 -m venv` 提示 `ensurepip is not available`：

```bash
sudo apt-get install -y python3.12-venv
```

### 1.4 环境变量文件（全链路验收需要）

```bash
# Linux / macOS / Git Bash
cp evn/.env.example evn/.env
# 编辑 evn/.env，至少填写 AICR_BOT_TOKEN、LLM_API_KEY、LLM_MODEL
```

Windows（PowerShell）：

```powershell
Copy-Item evn\.env.example evn\.env
notepad evn\.env
```

**仅跑冒烟测试**时可不创建 `evn/.env`。启动服务或调用真实 `/review` 时需要该文件。

---

## 2. 在本地 PC 上跑测试

### 2.1 一级验收：冒烟测试（推荐每次改代码后执行）

**不需要** GitLab、Docker、LLM 密钥。验证解析、分块、编排、脱敏、API 契约等 **29** 项逻辑。

#### Linux / macOS / Git Bash

```bash
cd <repo>/aicr-reviewer
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/smoke_test.py
```

#### Windows PowerShell

```powershell
cd <repo>\aicr-reviewer
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python scripts\smoke_test.py
```

**通过标准**：最后一行类似：

```text
All 29 smoke tests passed.
```

任一步断言失败会打印堆栈并退出，非零退出码。

#### 可选：语法检查

在仓库根目录：

```bash
python3 -m compileall -q aicr-reviewer/app aicr-reviewer/main.py
```

无输出即表示编译通过。

### 2.2 二级验收：本地 API 进程（仍可不连 GitLab）

1. 确保已执行上一节的 venv 与 `pip install`。
2. 启动服务：

| 系统 | 命令 |
|------|------|
| Linux / macOS | `cd <repo>/aicr-reviewer && ./scripts/run_local.sh` |
| Windows | `cd <repo>\aicr-reviewer` 后 `.\scripts\run_local.ps1` |

默认监听 **http://localhost:8001**（`GITLAB_URL` 默认为 `http://localhost:8000`，仅影响配置展示与后续 GitLab 调用）。

3. **健康检查**（新开一个终端）：

```bash
curl -s http://localhost:8001/health
# 期望: {"status":"ok"}
```

```bash
curl -s http://localhost:8001/health/detail
# 期望: status=ok，且可见 gitlab_url、llm_key_set 等字段
```

PowerShell 等价：

```powershell
(Invoke-WebRequest -Uri http://localhost:8001/health -UseBasicParsing).Content
```

**通过标准**：HTTP 200，且 `/health`  body 为 `{"status":"ok"}`。

> 说明：此时若未配置 `evn/.env` 中的密钥，`POST /review` 真实评审会失败；冒烟测试已在进程外覆盖 API 契约，无需为此重复调用。

---

## 3. 整体验收：分三个层级

按投入从低到高选择；**日常开发**完成 **L1** 即可合并；发版或联调前建议做到 **L2** 或 **L3**。

### L1 — 应用逻辑验收（约 5 分钟）

| 步骤 | 操作 | 通过标准 |
|------|------|----------|
| 1 | `python scripts/smoke_test.py` | `All 29 smoke tests passed.` |
| 2 | （可选）`compileall` | 无错误输出 |

**结论**：核心 Python 模块与 HTTP 契约符合设计；**不保证** GitLab/LLM 外网可用。

---

### L2 — 本地服务 + 配置探测（约 10 分钟）

在 L1 基础上：

| 步骤 | 操作 | 通过标准 |
|------|------|----------|
| 1 | `cp evn/.env.example evn/.env` 并填写密钥（见 [SECRETS.md](./SECRETS.md)） | 文件存在且非空关键项 |
| 2 | `run_local.sh` / `run_local.ps1` | 控制台无启动异常，uvicorn 监听 8001 |
| 3 | `GET /health`、`GET /health/detail` | 200；`token_set`、`llm_key_set` 与预期一致 |
| 4 | 本地仅调试 API 时可在 `.env` 设 `REVIEW_API_ALLOW_INSECURE=1` | `/health/detail` 中 `review_api_allow_insecure` 为 true |

**结论**：本机可运行评审服务，配置已加载；**尚未**验证 MR 评审与 GitLab 评论。

---

### L3 — 全链路 E2E（GitLab + LLM + MR/CI）

需要：**Docker**、足够磁盘与内存、有效 **LLM API**、GitLab **Bot Token**。

#### 3.1 启动 GitLab（Docker）

```bash
docker network create gitlab_default 2>/dev/null || true
cd <repo>/evn/gitlab
docker compose -f docker-compose.yml up -d
```

等待 GitLab 就绪（首次可能 10+ 分钟），浏览器访问：`http://localhost:8000`。

按 `evn/gitlab` 目录内说明或项目文档创建 Bot 用户、PAT，写入 `evn/.env` 的 `AICR_BOT_TOKEN`，`GITLAB_URL=http://localhost:8000`。

#### 3.2 启动 AICR Reviewer

**方式 A — 本机进程（与 L2 相同）**

```bash
cd <repo>/aicr-reviewer
./scripts/run_local.sh   # 或 Windows: .\scripts\run_local.ps1
```

**方式 B — Docker 与 GitLab 同网**

```bash
cd <repo>/aicr-reviewer
docker build -t gitlab-aicr-reviewer:latest .
cd <repo>/evn/gitlab
docker compose -f docker-compose.yml \
  -f ../../aicr-reviewer/deploy/docker-compose.aicr-reviewer.yml \
  up -d aicr-reviewer
```

此时 `GITLAB_URL` 在容器内通常为 `http://gitlab:8000`（见 [SECRETS.md](./SECRETS.md)）。

#### 3.3 真实 MR 评审验收

1. 将 `test_data/spring-cloud-demo/`（或业务仓库）推送到 GitLab。
2. 创建 **Merge Request**（含 `.java` 等可评审文件变更）。
3. 在业务仓库 CI 中配置 `aicr-reviewer/ci/gitlab-ci.snippet.yml` 同类 job，或手工调用：

```bash
export AICR_REVIEW_URL=http://localhost:8001
export AICR_REVIEW_SECRET=<与 evn/.env 中 REVIEW_API_SECRET 一致>
export CI_PROJECT_ID=<项目 ID>
export CI_MERGE_REQUEST_IID=<MR IID>

bash <repo>/aicr-reviewer/scripts/ci_review_gate.sh
```

4. 首次联调建议 `REVIEW_DRY_RUN=1`：只返回 API 结果、不向 MR 发评论，确认无异常后再改为 `0`。

| 检查项 | 通过标准 |
|--------|----------|
| `POST /review` | HTTP 200，JSON 含 `score`、`review_completed`、`summary` |
| 评审成功 | `review_completed=true`，`score` 为 0–100 实数 |
| GitLab MR（`REVIEW_DRY_RUN=0`） | 出现 AICR 摘要评论 / 行内讨论（视问题数量） |
| CI 门禁 | 仅当 `review_completed=true` 且 `score < AICR_SCORE_THRESHOLD` 时 job 失败 |
| Webhook（可选） | 配置 `GITLAB_WEBHOOK_SECRET` 后，MR open/update 返回 `accepted` |

#### 3.4 Webhook 抽检（可选）

```bash
curl -s -X POST http://localhost:8001/webhook/gitlab \
  -H "Content-Type: application/json" \
  -H "X-Gitlab-Token: <GITLAB_WEBHOOK_SECRET>" \
  -d '{"object_kind":"merge_request","object_attributes":{"action":"open","iid":1},"project":{"id":1}}'
```

期望：`{"status":"accepted",...}`（后台评审需有效 Token 与 LLM；失败时查服务日志）。

---

## 4. 验收清单（可打印勾选）

复制到 MR 描述或本地笔记中使用。

### 必做（L1）

- [ ] `cd aicr-reviewer && python scripts/smoke_test.py` → 29 项全部通过
- [ ] （可选）`compileall` 无报错

### 推荐（L2）

- [ ] `evn/.env` 已从 `evn/.env.example` 复制并填写
- [ ] `run_local` 启动成功，`GET /health` 返回 ok
- [ ] `GET /health/detail` 中 `token_set`、`llm_key_set` 符合预期

### 发版 / 联调（L3）

- [ ] GitLab CE（Docker）可访问 `http://localhost:8000`
- [ ] `AICR_BOT_TOKEN`、`LLM_API_KEY`、`LLM_MODEL` 有效
- [ ] 真实 MR 触发评审，`review_completed=true` 时分数合理
- [ ] `ci_review_gate.sh` 在低分且已完成评审时拦 MR，在 fail-open 场景放行
- [ ] （可选）Webhook 与 Runner 流水线端到端通过

---

## 5. 常见问题

| 现象 | 处理 |
|------|------|
| `ensurepip is not available` | Linux 安装 `python3.12-venv`（见 §1.3） |
| PowerShell 无法执行脚本 | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` |
| 端口 8001 被占用 | 结束旧 uvicorn 进程，或临时改 `run_local` 中的 `--port` |
| `/review` 返回 503「secret not configured」 | 设置 `REVIEW_API_SECRET`，或本地设 `REVIEW_API_ALLOW_INSECURE=1` |
| `/review` 返回 401 | Header 带 `X-AICR-Secret` 或 `Authorization: Bearer <secret>` |
| `review_completed=false` 且 summary 含 fail-open | LLM/GitLab/网络异常，CI **应放行**；查日志与 `evn/.env` |
| Docker 拉镜像慢 | 配置镜像加速；L1 不依赖 Docker |
| Windows 路径含中文或空格 | 尽量将仓库放在纯英文路径下 |

---

## 6. 相关文档

| 文档 | 内容 |
|------|------|
| [TESTING.md](./TESTING.md) | 冒烟用例矩阵、fail-open 语义、未覆盖项 |
| [SECRETS.md](./SECRETS.md) | 环境变量与密钥 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 系统架构与流水线 |
| [aicr-reviewer/README.md](../aicr-reviewer/README.md) | API 与 CI 片段 |
| [AGENTS.md](../AGENTS.md) | Cloud / 开发机快捷命令 |

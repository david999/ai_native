# Demo / 联调工程（test_data）

本目录用于 **独立的 Git 业务仓库**与**固定验收场景**，与 monorepo 分离版本管理。

## 布局

```
test_data/
├── spring-cloud-demo/          # 业务仓（自有 .git，clone 自本地 GitLab）
├── fixtures/scenarios/         # 固定测试场景（纳入 monorepo）
│   ├── manifest.yaml
│   ├── S01_clean_refactor/
│   └── ...
└── scripts/                    # 场景应用、MR、触发评审
    ├── apply_scenario.py
    ├── bootstrap_demo.ps1
    ├── ensure_gitlab.ps1
    └── ...
```

`spring-cloud-demo` 的 **remote 应指向本地 GitLab**（`http://localhost:8000/...`）。根 `.gitignore` 忽略 `test_data/**/.git/`。

## 获取 Demo

```bash
cd test_data
git clone http://localhost:8000/java_group/spring-cloud-demo.git
```

需先启动 `evn/gitlab`（`docker compose up -d`）。

## 固定测试场景

场景定义在 `fixtures/scenarios/`；**每次验收应用相同 patch**，不随机生成代码。详见 [docs/ACCEPTANCE_TESTING.md](../docs/ACCEPTANCE_TESTING.md)。

```powershell
cd E:\ai_native\aicr-reviewer
.\.venv\Scripts\python.exe ..\test_data\scripts\apply_scenario.py --scenario S02_npe_optional
```

基线分支：`aicr-test-base`（由 `bootstrap_demo.ps1` 创建）。

## CI 集成

业务仓库 `.gitlab-ci.yml` 引用：

- [`aicr-reviewer/ci/gitlab-ci.snippet.yml`](../aicr-reviewer/ci/gitlab-ci.snippet.yml)
- [docs/CI_REVIEW_PIPELINE.md](../docs/CI_REVIEW_PIPELINE.md)

| CI 变量 | 值 |
|---------|-----|
| `AICR_REVIEW_URL` | `http://host.docker.internal:8001`（Runner 容器 → 宿主机 AICR） |
| `AICR_REVIEW_SECRET` | 与 `evn/.env` 中 `REVIEW_API_SECRET` 一致 |

## 全链路验收

- 分层手册：[docs/LOCAL_PC_VERIFICATION.md](../docs/LOCAL_PC_VERIFICATION.md)
- 一键脚本：[docs/ACCEPTANCE_TESTING.md](../docs/ACCEPTANCE_TESTING.md)

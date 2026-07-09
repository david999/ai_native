# ocr-ci2 E2E 与样例仓

OCR Gateway 全链路 E2E 与 Java 样例业务仓均在本目录维护（自 ai_native `test_data/` 迁入）。

## 布局

| 路径 | 说明 |
|------|------|
| `e2e/ocr-gateway/` | D01–D06 自动化 E2E |
| `e2e/fixtures/datacalc-web/` | Java 样例仓（**git submodule**） |
| `scripts/acceptance/verify_gateway_runner.ps1` | 跑前检查（GitLab + Runner + Gateway） |
| `scripts/acceptance/create_or_update_mr.py` | MR 创建/查找 |

## Clone 与 submodule

```powershell
git clone --recurse-submodules <ocr-ci2-repo-url>
# 或已 clone 后：
cd ocr-ci2
git submodule update --init e2e/fixtures/datacalc-web
```

Submodule remote（生产 GitLab）：

```text
https://gitlab.aulton.com/java_group/datacalc-web.git
```

本地 GitLab（`:8000`）可在 `~/.gitconfig` 用 `insteadOf` 重定向：

```ini
[url "http://localhost:8000/"]
    insteadOf = https://gitlab.aulton.com/
```

## 基础设施（外部）

独立仓**不打包** GitLab / Runner 安装文件。本地联调可参考 ai_native monorepo 的 `evn/gitlab`，或通过环境变量指向已有实例：

| 变量 | 说明 |
|------|------|
| `OCR_MONOREPO_ROOT` | monorepo 根（用于定位 `evn/gitlab`） |
| `OCR_GITLAB_COMPOSE_DIR` | GitLab compose 目录 |
| `OCR_RUNNER_CONFIG` | Runner `config.toml` 路径 |

## 常用命令

```powershell
# 跑前检查
cd ocr-ci2
.\scripts\acceptance\verify_gateway_runner.ps1 -ProjectPath java_group/datacalc-web

# E2E 单元测试
cd e2e/ocr-gateway
python -m pytest -q

# 全链路
.\run_e2e.ps1 -Scenario D01_feature_date_guard
```

详见 [ocr-gateway/README.md](ocr-gateway/README.md) 与 [docs/独立仓库迁移检查清单.md](../docs/独立仓库迁移检查清单.md)。

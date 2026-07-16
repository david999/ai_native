# OCR GitLab CI

[Alibaba Open Code Review (OCR)](https://github.com/alibaba/open-code-review) **方案 2**：在 GitLab MR Pipeline 内执行 `ocr review` 并回写 MR 评论。

> **Gateway（方案 3）请用 [`ocr-ci2/`](../ocr-ci2/)**。本目录仅服务「CI Job 内跑 OCR」；勿用本目录的 `bake_ocr_config.py` 打 Gateway 生产镜像。

## 单一配置源（推荐）



本机只维护一份 **`%USERPROFILE%\.opencodereview\config.json`**（与 OCR CLI 相同路径）：



```json

{

  "llm": {

    "url": "https://example.com/v1/chat/completions",

    "auth_token": "YOUR_LLM_KEY",

    "model": "your-model",

    "use_anthropic": false

  },

  "gitlab": {

    "api_token": "glpat-..."

  }

}

```



| 字段 | 用途 |

|------|------|

| `llm.*` | `ocr review`（OCR 原生读取） |

| `gitlab.api_token` | MR 发帖（`post_ocr_to_gitlab.py`） |



构建镜像时复制进容器 `/root/.opencodereview/config.json`：



```powershell

cd ocr-ci

.\scripts\build_image.ps1

```



业务仓使用 [`gitlab-ci.ocr.snippet.baked.yml`](gitlab-ci.ocr.snippet.baked.yml)；**无需** GitLab CI Variables 传 LLM / GitLab token。



### 运行时优先级



```text

OCR LLM:  Job env OCR_LLM_*  >  config.json llm.*

GitLab:   Job env GITLAB_API_TOKEN  >  config.json gitlab.api_token  >  CI_JOB_TOKEN

```



## 目录与文件说明



| 路径 | 类型 | 作用 |

|------|------|------|

| [`Dockerfile`](Dockerfile) | 构建 | 基于 `node:20` 安装 OCR npm 包；COPY bake 后的 `config.json` 与发帖脚本 |

| [`.dockerignore`](.dockerignore) | 构建 | 缩小 build context；排除文档与本地验证产物 |

| [`.gitignore`](.gitignore) | Git | 忽略 `.build/` 本地生成物 |

| [`config/ocr-ci.config.json.example`](config/ocr-ci.config.json.example) | 文档 | 用户 `~/.opencodereview/config.json` 字段示例 |

| [`scripts/acceptance/bake_ocr_config.py`](scripts/acceptance/bake_ocr_config.py) | 构建辅助 | 将 `--config` / 用户 config **原样**写入 `.build/config.json`（无 defaults 合并） |

| [`scripts/build_image.ps1`](scripts/build_image.ps1) | 工具 | 调用 bake + `docker build -t ocr-ci:local` |

| [`scripts/ocr_ci_config.py`](scripts/ocr_ci_config.py) | 库 | 解析 `gitlab.api_token`（env / 镜像 config / 用户 config） |

| [`scripts/post_ocr_to_gitlab.py`](scripts/post_ocr_to_gitlab.py) | 运行时 | CI Job 读 `/tmp/ocr-result.json`，调 GitLab API 发行内评论 |

| [`scripts/acceptance/verify_local_ocr.py`](scripts/acceptance/verify_local_ocr.py) | 验收 | 本机 OCR + config + GitLab 连通性（不替代 CI） |
| [`tests/`](tests/) | 测试 | `pytest`：config 解析、bake 校验、发帖失败 note 文案 |
| [`requirements-dev.txt`](requirements-dev.txt) | 开发 | pytest 依赖 |

| [`gitlab-ci.ocr.snippet.baked.yml`](gitlab-ci.ocr.snippet.baked.yml) | CI 模板 | **推荐**：仅用镜像内 config，无 Variables |

| [`gitlab-ci.ocr.snippet.yml`](gitlab-ci.ocr.snippet.yml) | CI 模板 | 可选：GitLab Variables 覆盖 LLM（密钥不进镜像） |

| [`gitlab-ci.ocr.snippet.bootstrap.yml`](gitlab-ci.ocr.snippet.bootstrap.yml) | CI 模板 | 零镜像试用；每 Job `npm install` + 需复制发帖脚本到业务仓 |

| [`docs/本地部署指南.md`](docs/本地部署指南.md) | 文档 | 本地 GitLab + Runner + baked 镜像完整步骤 |

| `.build/config.json` | 生成 | `build_image.ps1` 产出，**含密钥**，勿提交 Git |

| `.build/ocr-result.json` | 生成 | 本地 `ocr review` / `verify_local_ocr.py` 调试输出 |



## 与 AICR 的关系



- **OCR CI**：配置在 `~/.opencodereview/config.json` + ocr-ci 镜像。

- **AICR 服务**（可选）：独立方案，见 `aicr-reviewer/`。



三方案对比见 [docs/OCR-GitLab-Webhook集成指南.md](../docs/OCR-GitLab-Webhook集成指南.md) §6。

**方案 3（OCR 常驻 + 轻 CI）**：见 [`ocr-ci2/`](../ocr-ci2/) 与 [项目汇报总结](../ocr-ci2/docs/项目汇报总结.md)。

## 开发与测试

```powershell
cd ocr-ci
pip install -r requirements-dev.txt
pytest
```

`build_image.ps1` 默认 `--require-secrets` 校验 bake 结果；跳过校验仅用于本地试验：`-SkipSecretCheck`。


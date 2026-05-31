# 外部 GitHub 项目参考说明

本文档说明 **AICR Reviewer** 在设计与实现时，是否参考了其他 GitHub 上的优秀开源项目，以及参考的原因。便于贡献者、审计与后续迭代时保持出处清晰。

---

## 1. 结论摘要

| 类别 | 说明 |
|------|------|
| **完整应用 / 同类产品** | 截至当前仓库版本，**未发现**对某一 GitHub 仓库进行 fork、子模块引入、整段源码复制，或在文档/提交说明中声明「功能设计直接来源于某项目」。 |
| **实现方式** | 评审流水线、GitLab 集成、CI 门禁、提示词与分块策略等，均为本仓库内 **自研实现**（见 `aicr-reviewer/app/`）。 |
| **依赖库** | 通过 PyPI 使用 FastAPI、python-gitlab、OpenAI SDK 等 **基础库**，属于常规技术选型，**不等同于**参考某一「AI 代码评审」类 GitHub 应用项目。 |

若未来从外部项目借鉴具体功能或代码片段，应在本文档对应章节补充：**项目链接、参考的功能点、原因、本仓库中的落点路径**。

---

## 2. 核查范围与方法

为得出上述结论，已对以下内容进行检索（截至文档编写时）：

- 全仓库 Markdown、Python 源码中的 `github.com`、inspiration、参考、fork 等关键词；
- `git log` 提交说明是否提及外部项目名；
- `.gitmodules`、子模块及 LICENSE/NOTICE 中的第三方归属；
- 既有文档（`README.md`、`docs/ARCHITECTURE.md`、`docs/CODE_REFERENCE.md` 等）。

**未纳入「功能参考」的范畴**：GitLab 官方 API/文档、OpenAI Chat Completions 协议说明、各云厂商 LLM 网关文档——这些属于产品与协议文档，而非「优秀 GitHub 项目」意义上的参考源。

---

## 3. 本仓库主要能力与参考状态

下表按 **本仓库已实现能力** 列出；「参考的 GitHub 项目」一栏如实记录当前状态（均为未直接参考）。

| 能力 | 本仓库实现位置（示例） | 是否参考了某 GitHub 项目 | 说明 |
|------|------------------------|--------------------------|------|
| GitLab MR diff/全文上下文拉取 | `app/gitlab/context_builder.py` | **否** | 基于 `python-gitlab` 调用 GitLab REST API，按业务需求组装 `MRContext`。 |
| Diff 分块与 token 预算 | `app/review/chunker.py` | **否** | 按字符估算与扩展名过滤的自研分块逻辑。 |
| Jinja2 提示词模板 | `app/review/prompt_renderer.py`、`templates/` | **否** | 模板与评审维度由本仓库维护。 |
| OpenAI 兼容 LLM 调用与 JSON 模式降级 | `app/llm/openai_compat.py` | **否** | 通用 Chat Completions 封装，非移植自某一评审产品仓库。 |
| 结构化评分/issue 解析 | `app/review/parser.py` | **否** | 约定 JSON schema 与校验逻辑为本仓库定义。 |
| 行内 discussion / MR note 发布 | `app/gitlab/publisher.py` | **否** | GitLab 讨论 API 的封装与失败回退策略自研。 |
| `POST /review`、Webhook、`fail-open` 门禁 | `app/api/routes.py`、`scripts/ci_review_gate.sh` | **否** | CI 仅在 `review_completed=true` 且低分时拦 MR，策略为本项目产品决策。 |
| 密钥脱敏 | `app/utils/redact.py` | **否** | 发送 LLM 前的简单脱敏规则。 |
| 冒烟与分层测试 | `scripts/smoke_test.py`、`docs/TESTING.md` | **否** | 测试矩阵随本仓库演进。 |

**总结**：上表能力均未标注为来自某一特定 GitHub 应用仓库；业界存在功能相似的开源/商业产品（见第 5 节），但 **本仓库未将其列为已采用的参考来源**。

---

## 4. 使用的开源依赖（库级，非「评审产品」参考）

以下为 `aicr-reviewer/requirements.txt` 中的主要依赖。选用原因是工程上的通用实践，**不是因为复制了某个 AI Code Review 类 GitHub 项目的架构**。

| 依赖 | 仓库（GitHub） | 在本项目中的用途 |
|------|----------------|------------------|
| [FastAPI](https://github.com/fastapi/fastapi) | `fastapi/fastapi` | HTTP API、路由、依赖注入 |
| [Uvicorn](https://github.com/Kludex/uvicorn) | `Kludex/uvicorn` | ASGI 服务进程 |
| [python-gitlab](https://github.com/python-gitlab/python-gitlab) | `python-gitlab/python-gitlab` | GitLab API 客户端 |
| [OpenAI Python SDK](https://github.com/openai/openai-python) | `openai/openai-python` | OpenAI 兼容 Chat Completions |
| [Jinja2](https://github.com/pallets/jinja) | `pallets/jinja` | 提示词模板渲染 |
| [Pydantic](https://github.com/pydantic/pydantic) | `pydantic/pydantic` | 请求/响应模型（随 FastAPI 使用） |

---

## 5. 同类生态项目（延伸阅读，非本仓库引用来源）

下列项目在业界常与「MR + LLM 自动评审」一并讨论，功能上可能与 AICR 的部分能力 **概念相近**。列出它们仅便于读者对比学习，**不代表本仓库曾参考或移植其代码**；亦未在源码中建立对应关系。

| 项目（示例） | 典型能力 | 与本仓库关系 |
|--------------|----------|--------------|
| [Qodo-AI/pr-agent](https://github.com/Qodo-AI/pr-agent)（原 CodiumAI） | 多平台 PR 分析、建议、Changelog 等 | **未参考**；本仓库专注 GitLab + 自托管部署场景。 |
| [coderabbitai/ai-pr-reviewer](https://github.com/coderabbitai/ai-pr-reviewer) 等 | GitHub Action 驱动的 PR 评审 | **未参考**；触发链路与平台不同（GitLab CI/Webhook）。 |
| [reviewdog/reviewdog](https://github.com/reviewdog/reviewdog) | 将 linter 结果以 review comment 呈现 | **未参考**；AICR 以 LLM 语义评审为主，非 linter 聚合。 |
| 各类 `*-gpt-review` / `llm-code-review` 示例仓库 | 最小化 demo | **未参考**；本仓库为完整服务化实现（编排、发布、门禁）。 |

若团队在评审流程上**主动决定**采纳某一开源项目的交互或提示词结构，请回到本文档第 1 节表格中 **新增一行**，写清参考原因与在本仓库的映射文件。

---

## 6. 后续维护约定

1. **引入外部代码**（复制、改编）时：在 PR 中说明来源仓库与 commit/版本，并更新本文档对应能力行。
2. **仅概念借鉴**（未复制代码）时：同样记录「借鉴点 + 原因」，避免与「零参考」混淆。
3. **依赖升级**：仅需更新第 4 节表格中的版本/链接说明，无需声称参考了评审类产品。

---

## 7. 相关文档

| 文档 | 说明 |
|------|------|
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 系统架构与评审流水线 |
| [LLM_CODE_REVIEW.md](./LLM_CODE_REVIEW.md) | 大模型评审流程与提示词 |
| [CODE_REFERENCE.md](./CODE_REFERENCE.md) | 源码级模块说明 |

# 外部 GitHub 项目参考说明

本文档说明 **AICR Reviewer** 在设计与实现时，参考了哪些 GitHub 生态中的优秀开源项目，以及**概念借鉴点**与**本仓库落点**。便于贡献者、审计与后续迭代时保持出处清晰。

> **说明**：下述均为**概念与交互借鉴**，在 `aicr-reviewer/app/` 内**自研实现**；未 fork、未子模块、未整段复制 pr-agent / ai-pr-reviewer / reviewdog 等仓库源码。

---

## 1. 结论摘要

| 类别 | 说明 |
|------|------|
| **代码关系** | 无对上述「AI 评审类产品」仓库的 fork 或源码移植；实现基于 FastAPI + python-gitlab + OpenAI 兼容 API。 |
| **概念参考** | 阶段 A/B/C 多项能力在公开文档对比后，**有意借鉴** pr-agent、ai-pr-reviewer、reviewdog 的成熟做法，并在本文件登记。 |
| **依赖库** | FastAPI、python-gitlab、OpenAI SDK、tiktoken 等为 PyPI 常规选型，**不等同于**参考某一评审应用仓库。 |

---

## 2. 参考项目一览

| 项目 | 链接 | 借鉴性质 |
|------|------|----------|
| **pr-agent** | [the-pr-agent/pr-agent](https://github.com/the-pr-agent/pr-agent) | PR 压缩、tiktoken、多工具（describe/changelog）、`configuration.toml`、self-reflection |
| **ai-pr-reviewer** | [coderabbitai/ai-pr-reviewer](https://github.com/coderabbitai/ai-pr-reviewer) | 按 commit/SHA 增量评审、MR 摘要、**评论对话**（@bot） |
| **reviewdog** | [reviewdog/reviewdog](https://github.com/reviewdog/reviewdog) | **仅 diff 内**呈现问题、CI 中 linter → 评审类工具串联 |
| **典型 llm-code-review demo** | 各类小仓库 | 未借鉴架构；本仓库为完整服务化 + GitLab 门禁 |

**未纳入「功能参考」**：GitLab 官方 API、OpenAI Chat Completions 协议、云厂商 LLM 网关文档。

---

## 3. 已实现能力与参考出处（阶段 A / B / C）

下表对应 [GITHUB_REFERENCES 原 §8.4 路线图](https://github.com/david999/ai_native/blob/master/docs/GITHUB_REFERENCES.md) 中已落地项（截至阶段 C PR）。

| 阶段 | 能力 | 主要借鉴来源 | 借鉴的优秀做法 | 本仓库落点 |
|------|------|--------------|----------------|------------|
| **A** | tiktoken 分块 | pr-agent | Token-aware 装入 prompt，避免粗算超限 | `token_utils.py`, `chunker.py`, `REVIEW_USE_TIKTOKEN` |
| **A** | 语言/路径优先级 | pr-agent | 主业务语言文件优先占满 context | `language_priority.py`, `chunker.py` |
| **A** | diff 压缩（删-only hunk、合并删除列表） | pr-agent | 大 PR 降噪、省 token | `diff_compress.py`, `context_builder.py` |
| **A** | 增量评审 `last_reviewed_sha` | ai-pr-reviewer | 仅评新 commit 区间，减重复 | `review_state.py`, `context_builder._fetch_changes` |
| **A** | 并行 chunk、head 未变跳过 | 工程实践 + ai-pr-reviewer | 降延迟、避免无意义 LLM 调用 | `orchestrator.py`, `config.py` |
| **A** | CI：reviewdog → AICR 文档 | reviewdog | 先确定性 linter、再语义 LLM | `docs/CI_REVIEW_PIPELINE.md`, `ci/gitlab-ci.snippet.yml` |
| **B** | diff hunk 内过滤 issue | reviewdog | 只保留 diff 可定位的发现，减幻觉行号 | `diff_line_index.py`, `AICR_FILTER_ISSUES_TO_DIFF` |
| **B** | self-reflection | pr-agent | 二次 pass 降误报/漏报 | `reflection.py`, `prompts/reflection_*.j2` |
| **B** | 多语言 `system_*.j2` | pr-agent / 通用实践 | 按扩展名选模板，非写死 Spring | `prompts/system_*.j2`, `resolve_system_template()` |
| **B** | 过滤后分数 reconcile | 自研（受 pr-agent 质量思路启发） | 过滤幻觉 issue 后分数与剩余 severity 一致 | `score_utils.py`, `orchestrator._finalize_findings` |
| **B** | MR 元数据防注入 | 安全通用实践 | 不可信标题/描述包在 XML 边界内 | `user_review.j2`, `reflection_*.j2`, 阶段 C 工具模板 |
| **C** | describe（MR 描述） | pr-agent `/describe` | 从 diff 生成 MR 说明，减轻人工 | `tools/describe.py`, `POST /describe`, `prompts/describe_*.j2` |
| **C** | CHANGELOG note | pr-agent changelog 工具 | 发布结构化变更记录 | `tools/changelog.py`, `POST /changelog`, `mr_actions.upsert_changelog_note` |
| **C** | 评论对话 | ai-pr-reviewer | Note webhook + `@bot` 触发问答 | `tools/ask.py`, Note `webhook`, `prompts/ask_*.j2` |
| **C** | `config.toml` | pr-agent `configuration.toml` | 部署/仓库级配置，env 优先 | `config_toml.py`, `config_resolver.py`, `evn/.aicr/config.toml.example` |
| **C** | 按工具 LLM 配置 | ai-pr-reviewer 轻/重模型分工 | describe/changelog/ask 不同 temperature/model | `create_llm_for_tool()`, `[llm.describe]` 等 |
| **C** | describe 后抑制 webhook 全量 review | 自研（避免 ai-pr-reviewer 式重复评） | 写回 MR 后短时跳过 `update` 触发的 review | `review_state.set_suppress_webhook_review`, `AICR_SUPPRESS_REVIEW_AFTER_DESCRIBE` |
| **C** | CHANGELOG note 去重 | ai-pr-reviewer 跨次去重思路 | 更新已有 `## AICR Changelog` note | `GitLabMRActions.upsert_changelog_note` |

详细用法见 [PHASE_C.md](./PHASE_C.md)、[CI_REVIEW_PIPELINE.md](./CI_REVIEW_PIPELINE.md)、[ARCHITECTURE.md](./ARCHITECTURE.md)。

---

## 4. 分项目：借鉴了什么、未照搬什么

### 4.1 pr-agent

| 借鉴的优秀部分 | 本仓库做法 | 未照搬 |
|----------------|------------|--------|
| PR Compression（语言优先级、删-only hunk） | 阶段 A `diff_compress` + `language_priority` | 未引入其完整多工具 CLI |
| tiktoken 预算 | 阶段 A `token_utils` / `chunker` | 未使用其 TOML 全量 prompt 仓库 |
| Self-reflection | 阶段 B `reflection.py` | 未引入其 `/improve`、`/ask` 等全部工具 |
| describe / changelog | 阶段 C 独立 HTTP 工具 + Jinja2 | 未绑定 GitHub App；仅 GitLab |
| `configuration.toml` | `evn/.aicr/config.toml` + `.aicr/config.toml` | 密钥仍在 `evn/.env` |

### 4.2 ai-pr-reviewer

| 借鉴的优秀部分 | 本仓库做法 | 未照搬 |
|----------------|------------|--------|
| 按 SHA / 增量只评新变更 | 阶段 A `repository_compare` + `last_reviewed_sha` | 未实现「琐碎 MR 自动跳过」 |
| PR 摘要类能力 | 阶段 C describe（可选写回 MR） | 未使用其 GitHub Action 分发模型 |
| 评论对话 | 阶段 C Note webhook + `@aicr` / `/ask` | 未实现 GitHub PR review thread 全功能 |
| 轻/重模型 | 阶段 C `[llm.*]` / `LLM_MODEL_DESCRIBE` | 仍为单 provider 封装，非双进程 |

### 4.3 reviewdog

| 借鉴的优秀部分 | 本仓库做法 | 未照搬 |
|----------------|------------|--------|
| 仅对 diff 内行评论 | 阶段 B `filter_issues_to_diff` | 未集成 golangci/eslint 等 reporter |
| CI 流水线位置 | 文档建议 reviewdog job → AICR job | 未内嵌 reviewdog 二进制 |
| code suggestion 形态 | 未实现 | 可选后续在 `publisher` 增加 suggestion 块 |

---

## 5. 横切能力现状矩阵（更新）

| 能力 | 状态 | 主要参考 |
|------|------|----------|
| Token 精确预算 | ✅ 已实现 | pr-agent |
| 大 PR 压缩 | ✅ 已实现 | pr-agent |
| 增量评审（SHA） | ✅ 已实现 | ai-pr-reviewer |
| Self-reflection | ✅ 已实现 | pr-agent |
| 仅 diff 内 issue | ✅ 已实现 | reviewdog |
| 多语言 system 模板 | ✅ 已实现 | pr-agent |
| MR describe / CHANGELOG | ✅ 已实现 | pr-agent / ai-pr-reviewer |
| 评论对话 | ✅ 已实现 | ai-pr-reviewer |
| config.toml | ✅ 已实现 | pr-agent |
| 轻/重模型分工 | ⚠️ 部分（按工具 model/temperature） | ai-pr-reviewer |
| Linter + LLM 同仓编排 | ⚠️ 文档级（CI 串联） | reviewdog |
| Code suggestion 块 | ❌ 未实现 | reviewdog |
| trivial MR 跳过 | ❌ 未实现 | ai-pr-reviewer |
| pr-agent 全工具面 | ❌ 未实现 | pr-agent |

---

## 6. 本仓库相对优势（保持）

- **GitLab 自托管一体化**：FastAPI + `python-gitlab` + `review_completed` fail-open 门禁（`ci_review_gate.sh`）。
- **项目规范**：业务仓 `.llm/CONTEXT.md`；部署/项目 `.aicr/config.toml`。
- **发布容错**：行内 discussion → MR note 回退；同批次 fingerprint 去重。
- **安全**：`redact_secrets`、评审 API / Webhook 鉴权、不可信 MR 元数据边界。

---

## 7. 明确不建议借鉴的做法

| 做法 | 来源 | 原因 |
|------|------|------|
| LLM 失败即拦 MR | 部分 Action | 与 AICR fail-open 产品定位冲突 |
| 无说明的多块 `min(score)` | — | 已在 summary 与 `score_utils` reconcile 中缓解 |
| 整仓 fork pr-agent | pr-agent | 维护与 GitLab 适配成本高 |
| 仅 LLM、禁用 linter | — | 应用 reviewdog 处理确定性问题 |

---

## 8. 维护约定

1. **新概念借鉴**：在本文 **§3 表格** 增行，写清来源项目、借鉴点、落点路径。
2. **复制外部代码**：PR 中注明来源 commit/许可证，并更新 §3。
3. **依赖升级**：仅需维护 PyPI 依赖表（见历史版本或 README），无需声称参考评审类产品。

---

## 9. 相关文档

| 文档 | 说明 |
|------|------|
| [CODE_REFERENCE.md](./CODE_REFERENCE.md) | 源码级模块与函数索引 |
| [ARCHITECTURE.md](./ARCHITECTURE.md) | 架构与流水线 |
| [PHASE_C.md](./PHASE_C.md) | 阶段 C API 与配置 |
| [CI_REVIEW_PIPELINE.md](./CI_REVIEW_PIPELINE.md) | CI 与 reviewdog 串联 |
| [LLM_CODE_REVIEW.md](./LLM_CODE_REVIEW.md) | 提示词与评审语义 |

---

*最后更新：阶段 A/B/C 已合并路线图能力；与 `aicr-reviewer` 冒烟测试 70 项同步。*

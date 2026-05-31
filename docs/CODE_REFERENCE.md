# AICR Reviewer 代码详细说明

本文档在 [ARCHITECTURE.md](ARCHITECTURE.md) 与 [LLM_CODE_REVIEW.md](LLM_CODE_REVIEW.md) 的基础上，从**源码层级**描述模块职责、类与函数、数据结构、控制流分支与异常路径。面向需要修改评审逻辑、接入新 LLM、或排查 CI/Webhook 行为的开发者。

**相关文档**

| 文档 | 侧重 |
|------|------|
| [ARCHITECTURE.md](ARCHITECTURE.md) | 组件关系、流水线概览、失败策略表 |
| [LLM_CODE_REVIEW.md](LLM_CODE_REVIEW.md) | LLM 提示词、门禁语义、运维建议 |
| [SECRETS.md](SECRETS.md) | 环境变量与安全 |
| [aicr-reviewer/README.md](../aicr-reviewer/README.md) | 部署、API、本地启动 |

---

## 1. 源码树与包依赖

### 1.1 Monorepo 布局

```
/workspace                          # 仓库根（config 中 _MONOREPO_ROOT）
├── evn/.env                        # 推荐的环境变量（不提交密钥）
├── docs/                           # 架构与本文档
├── aicr-reviewer/                  # FastAPI 应用根（uvicorn 工作目录）
│   ├── main.py                     # FastAPI app 工厂
│   ├── requirements.txt
│   ├── app/
│   │   ├── config.py               # 环境变量加载（模块 import 时执行）
│   │   ├── exceptions.py
│   │   ├── api/routes.py           # HTTP 入口
│   │   ├── gitlab/
│   │   │   ├── client.py           # python-gitlab 单例
│   │   │   ├── context_builder.py  # MR → MRContext
│   │   │   └── publisher.py        # 评论发布
│   │   ├── llm/
│   │   │   ├── base.py             # LLMProvider Protocol
│   │   │   ├── factory.py
│   │   │   └── openai_compat.py
│   │   ├── review/
│   │   │   ├── orchestrator.py     # 流水线主编排
│   │   │   ├── chunker.py
│   │   │   ├── parser.py
│   │   │   ├── prompt_renderer.py
│   │   │   └── prompts/*.j2
│   │   └── utils/redact.py
│   └── scripts/
│       ├── ci_review_gate.sh       # CI 门禁（Runner 侧）
│       └── smoke_test.py           # 无 GitLab 的单元级冒烟
```

### 1.2 模块依赖方向（只允许向下依赖）

```mermaid
flowchart TB
    main[main.py]
    routes[api.routes]
    orch[review.orchestrator]
    cb[gitlab.context_builder]
    pub[gitlab.publisher]
    glc[gitlab.client]
    llmf[llm.factory]
    llmo[llm.openai_compat]
    cfg[config]
    exc[exceptions]
    chunk[review.chunker]
    pr[review.prompt_renderer]
    par[review.parser]
    red[utils.redact]

    main --> routes
    routes --> orch
    routes --> cb
    routes --> llmf
    routes --> pub
    routes --> cfg
    routes --> exc
    orch --> cb
    orch --> pub
    orch --> chunk
    orch --> pr
    orch --> par
    orch --> red
    orch --> cfg
    orch --> exc
    cb --> glc
    cb --> cfg
    cb --> red
    pub --> glc
    pub --> cfg
    llmf --> llmo
    llmf --> cfg
    glc --> cfg
```

**约定**：业务代码不直接 `os.getenv`，统一 `from app.config import ...`。GitLab 客户端通过 `get_gitlab_client()` 单例获取，避免重复建连。

---

## 2. 应用入口：`main.py`

| 项 | 说明 |
|----|------|
| 框架 | FastAPI |
| 版本 | `2.0.0`（`app` 元数据） |
| 路由挂载 | `app.include_router(router)`，`router` 来自 `app.api.routes`（无 URL 前缀） |
| 日志 | `logging.basicConfig(level=INFO)`，logger 名多为 `aicr` |

启动示例（工作目录必须为 `aicr-reviewer/`）：

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```

`import main` 时会间接加载 `app.config`（执行 `_load_env_files()`），因此**在 import 任何 `app.*` 之前**应已存在 `evn/.env` 或等价文件。

---

## 3. 配置层：`app/config.py`

### 3.1 加载时机与顺序

模块顶层调用 `_load_env_files()`，对以下路径依次 `load_dotenv(path, override=False)`：

1. `<repo>/evn/.env`
2. `<repo>/.env`
3. `aicr-reviewer/.env`

`override=False` 表示：**先被加载的变量优先**；后出现的文件不会覆盖已存在的环境变量。

`_MONOREPO_ROOT` 计算方式：`Path(__file__).resolve().parents[2]`（`app/config.py` → `app` → `aicr-reviewer` → 仓库根）。

### 3.2 导出常量一览

| 常量 | 环境变量 | 默认值 | 使用方 |
|------|----------|--------|--------|
| `GITLAB_URL` | `GITLAB_URL` | `http://localhost:8000` | `client.py` |
| `AICR_BOT_TOKEN` | `AICR_BOT_TOKEN` | `""` | GitLab 客户端；`/review` 未配置时 500 |
| `SCORE_THRESHOLD` | `AICR_SCORE_THRESHOLD` | `60` | `publisher.publish_summary`、与 CI 脚本一致 |
| `REVIEW_API_SECRET` | `REVIEW_API_SECRET` | `""` | `/review` 鉴权；空则跳过 |
| `LLM_PROVIDER` | `LLM_PROVIDER` | `ctyun_openai` | `factory.py` |
| `LLM_API_BASE` | `LLM_API_BASE` | 天翼预设 URL | 可覆盖 preset |
| `LLM_API_KEY` | `LLM_API_KEY` | `""` | 必填（factory 校验） |
| `LLM_MODEL` | `LLM_MODEL` | `""` | 必填 |
| `LLM_TIMEOUT_SECONDS` | `LLM_TIMEOUT_SECONDS` | `120` | OpenAI 客户端 |
| `LLM_MAX_TOKENS` | `LLM_MAX_TOKENS` | `4096` | completion 上限 |
| `LLM_TEMPERATURE` | `LLM_TEMPERATURE` | `0.2` | 偏低以利 JSON 稳定 |
| `REVIEW_MAX_INPUT_TOKENS` | `REVIEW_MAX_INPUT_TOKENS` | `12000` | `DiffChunker` |
| `CONTEXT_MAX_CHARS` | `CONTEXT_MAX_CHARS` | `8000` | `.llm/CONTEXT.md` 截断 |
| `REVIEW_DRY_RUN` | `REVIEW_DRY_RUN` | `0`（`1` 为真） | 跳过 `GitLabPublisher` |
| `GITLAB_WEBHOOK_SECRET` | `GITLAB_WEBHOOK_SECRET` | `""` | Webhook 校验 |
| `GITLAB_WEBHOOK_ALLOW_INSECURE` | `GITLAB_WEBHOOK_ALLOW_INSECURE` | `0` | 无 secret 时是否允许 |

---

## 4. 异常体系：`app/exceptions.py`

```text
Exception
└── ReviewError                    # 评审失败基类
    ├── LLMReviewError             # LLM 调用或解析失败
    └── NoReviewableChangesError   # 无支持扩展名的可审变更
```

| 异常 | 抛出位置 | API 层处理 | `review_completed` | `score` |
|------|----------|------------|----------------------|---------|
| `NoReviewableChangesError` | `orchestrator.run`（chunks 为空） | `routes.review` 专用分支 | `false` | `100` |
| `LLMReviewError` | 全部分块 LLM 失败；或 `_review_chunk` 包装 | `_fail_open_review` | `false` | `100` |
| `ReviewError` | 其它继承（当前较少直接抛） | `_fail_open_review` | `false` | `100` |
| `HTTPException` | `_run_orchestrator`（token/LLM 未配置） | `_fail_open_review` | `false` | `100` |
| 任意 `Exception` | 未预期错误 | `_fail_open_review` + `exc_info` | `false` | `100` |

注意：`exceptions.py` 注释写 `ReviewError`「不应作为 score=100」，但 **`routes.py` 将 `ReviewError` 与 `LLMReviewError` 一并 fail-open**。实际行为以 `routes.py` 为准。

---

## 5. HTTP 层：`app/api/routes.py`

### 5.1 数据模型（Pydantic）

**`ReviewRequest`**

| 字段 | 类型 | 默认 | 含义 |
|------|------|------|------|
| `project_id` | `int` | 必填 | GitLab 项目 ID |
| `mr_iid` | `int` | 必填 | MR 内部 IID（`!123` 中的 123） |
| `diff` | `str` | `""` | CI 注入的额外 patch，见 `ContextBuilder.build(extra_diff)` |

**`ReviewResult`**

| 字段 | 类型 | 默认 | 含义 |
|------|------|------|------|
| `score` | `float` | — | 0–100；fail-open 时为 **100** |
| `issues` | `List[Dict]` | — | 结构化问题 |
| `code_quality` | `List[Dict]` | `[]` | Code Climate 风格，供工具链 |
| `summary` | `str` | `""` | 人类可读摘要 |
| `review_completed` | `bool` | `False` | **CI 门禁唯一可信标志** |

常量：`FAIL_OPEN_SCORE = 100.0`。

### 5.2 `GET /health`

无鉴权。返回运行态探测字段（不调用 GitLab/LLM）：

- `status`: `"ok"`
- `gitlab_url`, `token_set`, `llm_provider`, `llm_model`, `llm_key_set`, `review_auth_required`

### 5.3 `POST /review` — 完整决策树

```mermaid
flowchart TD
    Start([POST /review]) --> Auth{_verify_review_auth}
    Auth -->|HTTPException| FO1[_fail_open_review]
    Auth -->|通过| Run[_run_orchestrator]
    Run -->|NoReviewableChangesError| NR[ReviewResult score=100 completed=false]
    Run -->|HTTPException| FO2[_fail_open_review]
    Run -->|LLMReviewError / ReviewError| FO3[_fail_open_review]
    Run -->|Exception| FO4[_fail_open_review + log]
    Run -->|成功 dict| OK[ReviewResult completed=true]
    FO1 --> R200[HTTP 200]
    FO2 --> R200
    FO3 --> R200
    FO4 --> R200
    NR --> R200
    OK --> R200
```

**鉴权 `_verify_review_auth`**

1. `REVIEW_API_SECRET` 为空 → **直接通过**（本地开发）。
2. 否则读取 `X-AICR-Secret`；若空则解析 `Authorization: Bearer <token>`。
3. 不匹配 → `HTTPException(401)`；**注意**：`review()` 捕获后 **不返回 401**，而是 `_fail_open_review`（fail-open）。

**`_run_orchestrator`**

1. `AICR_BOT_TOKEN` 空 → `HTTPException(500)` → 上层 fail-open。
2. `create_llm_provider()` → `ValueError` → `HTTPException(503)` → fail-open。
3. 构造 `ReviewOrchestrator(ContextBuilder(), llm, GitLabPublisher())`。
4. 调用 `orchestrator.run(project_id, mr_iid, extra_diff)`。

### 5.4 `POST /webhook/gitlab` — 分支说明

与 `/review` 不同：**鉴权失败返回真实 401/503**，不 fail-open（Webhook 由 GitLab 重试，不阻塞 MR 合并）。

| 步骤 | 条件 | 响应 |
|------|------|------|
| Secret | 未配置且 `GITLAB_WEBHOOK_ALLOW_INSECURE=0` | **503** |
| Secret | 已配置但 `X-Gitlab-Token` 不匹配 | **401** |
| 事件类型 | `object_kind != "merge_request"` | 200 `ignored` |
| MR 动作 | `action` 不在 `open`,`update`,`reopen` | 200 `ignored` |
| 参数 | 缺 `project.id` 或 `object_attributes.iid` | 200 `ignored` |
| 成功受理 | 以上均通过 | 200 `accepted` + BackgroundTasks |

后台任务 `_run_review()`：

- 调用 `_run_orchestrator`（与同步 `/review` 相同逻辑）。
- **任意异常仅打日志**，不向 GitLab 返回错误（HTTP 已结束）。

---

## 6. GitLab 集成层

### 6.1 `app/gitlab/client.py`

```python
_gl_instance: Optional[gitlab.Gitlab] = None

def get_gitlab_client() -> gitlab.Gitlab:
    # 懒加载单例：Gitlab(GITLAB_URL, private_token=AICR_BOT_TOKEN)
```

全进程共享一个 `python-gitlab` 实例；**非线程安全重建**（Cloud 部署通常单 worker 或可接受）。

### 6.2 `MRContext` 与 `ContextBuilder`

#### `MRContext`（`__slots__` 数据载体）

| 属性 | 类型 | 来源 |
|------|------|------|
| `project_id`, `mr_iid` | `int` | 参数 |
| `title`, `description` | `str` | `mr.title`, `mr.description` |
| `source_branch`, `target_branch` | `str` | MR API |
| `diff_refs` | `dict \| None` | `mr.diff_refs`（行内评论必需） |
| `changes` | `list` | `mr.changes()["changes"]` |
| `context_md` | `str` | `.llm/CONTEXT.md` 或默认 Spring 文案 |
| `changed_files` | `list[dict]` | 见下表 |

#### `changed_files` 每项结构

| 键 | 说明 |
|----|------|
| `old_path`, `new_path` | GitLab change 对象 |
| `diff` | unified diff 字符串 |
| `content` | 源分支完整文件（UTF-8，`errors=ignore`） |
| `is_supported` | 路径是否以 `SUPPORTED_EXTENSIONS` 结尾 |

**`SUPPORTED_EXTENSIONS`（模块级常量）**

```text
.java, .kt, .xml, .yml, .yaml, .properties,
.py, .js, .ts, .go, .rs, .sql,
.dockerfile, .gradle, .toml
```

#### `build()` 执行顺序

```mermaid
sequenceDiagram
    participant CB as ContextBuilder
    participant GL as GitLab API
    participant MR as MRContext

    CB->>GL: projects.get + mergerequests.get
    CB->>GL: mr.changes()
    loop 每个 change
        CB->>CB: 判断 is_supported
        alt supported 且有 new_path
            CB->>GL: files.raw(new_path, source_branch)
        end
        CB->>MR: append changed_files[]
    end
    alt extra_diff 非空
        CB->>MR: insert 伪文件 _ci_extra_diff.patch
    end
    CB->>CB: _load_context_md + redact_secrets
    CB->>MR: 填充 context_md
```

**`_load_context_md` 分支**

1. 依次尝试 `ref = source_branch`、`target_branch`。
2. 读取 `.llm/CONTEXT.md`；超长则截断至 `CONTEXT_MAX_CHARS` 并 `warning` 日志。
3. 两分支均失败 → `_default_context()`（内置 Spring Boot/Cloud 约定列表）。

**`extra_diff`（CI 注入）**

在 `changed_files` **头部**插入：

```python
{
  "old_path": "",
  "new_path": "_ci_extra_diff.patch",
  "diff": extra_diff,
  "content": "",
  "is_supported": True,
}
```

用于 Runner 侧附带 CI 生成补丁而 GitLab changes API 未包含的场景。

### 6.3 `GitLabPublisher`

#### 实例状态

- `_seen: set` — 本批次已发布 fingerprint（`publish_issue` 生命周期 = 单次 `ReviewOrchestrator.run` 内新建 Publisher）。

#### `publish_issue` 分支

```mermaid
flowchart TD
    A[publish_issue] --> B{fingerprint 已见?}
    B -->|是| Skip[debug 日志跳过]
    B -->|否| C[加入 _seen]
    C --> D{file_path 且 diff_refs 且 line>0?}
    D -->|是| E[_post_inline discussions.create]
    E -->|成功| Done[return]
    E -->|异常| F[_post_note 回退]
    D -->|否| F
    F --> G[notes.create 含位置说明]
```

**行内 `_post_inline` position 结构**

```python
{
  "base_sha": diff_refs["base_sha"],
  "start_sha": diff_refs["start_sha"],
  "head_sha": diff_refs["head_sha"],
  "position_type": "text",
  "new_path": file_path,
  "new_line": new_line,
}
```

模型若给出不在 MR diff 范围内的行号，GitLab API 失败 → 自动 Note 回退。

#### `publish_summary`

- `status = "PASSED" if score >= threshold else "FAILED"`
- 通过 `mr.notes.create` 发布 Markdown 摘要（分数、阈值、issue 数、summary 正文）。

---

## 7. LLM 层

### 7.1 `LLMProvider`（`app/llm/base.py`）

`typing.Protocol`，约定：

```python
def chat(
    self,
    messages: List[Dict[str, str]],  # OpenAI 风格 role/content
    *,
    json_mode: bool = True,
    max_tokens: Optional[int] = None,
    temperature: Optional[float] = None,
) -> str:  # 模型原始文本（期望 JSON）
```

便于测试注入 `MagicMock`。

### 7.2 `create_llm_provider`（`factory.py`）

**预设 `_PROVIDER_MAP`**

| `LLM_PROVIDER` | 默认 `api_base` |
|----------------|-----------------|
| `ctyun_openai` | `https://wishub-x6.ctyun.cn/v1` |
| `deepseek` | `https://api.deepseek.com/v1` |
| `zhipu` | `https://open.bigmodel.cn/api/paas/v4` |
| `openai` | `https://api.openai.com/v1` |

解析规则：

- `api_base = LLM_API_BASE or preset["api_base"]`
- 三者 `api_base`、`LLM_API_KEY`、`LLM_MODEL` 缺一 → `ValueError`

返回 `OpenAICompatibleProvider` 实例（structural subtyping，未显式 inherit Protocol）。

### 7.3 `OpenAICompatibleProvider.chat` 分支

```mermaid
flowchart TD
    Start[chat json_mode=True] --> Try[create with response_format json_object]
    Try -->|成功| Ret[返回 content]
    Try -->|异常| Check{_json_mode_unsupported?}
    Check -->|是| Retry[无 response_format 重试]
    Check -->|否| Raise[向上抛出]
    Retry --> Ret
```

`_json_mode_unsupported`：异常消息含 `response_format`、`json_object` 或 `unsupported`（大小写不敏感）。

日志记录 `usage.prompt_tokens` / `completion_tokens` / `total_tokens`（若 API 返回）。

---

## 8. 评审核心：`ReviewOrchestrator`

文件：`app/review/orchestrator.py`。这是**业务主路径**，建议修改行为时从此读起。

### 8.1 依赖注入（构造函数）

| 参数 | 默认实现 | 职责 |
|------|----------|------|
| `context_builder` | `ContextBuilder()` | 构建 `MRContext` |
| `llm_provider` | `create_llm_provider()` | 每块一次 `chat` |
| `publisher` | `GitLabPublisher()` | 非 dry-run 时写 GitLab |

内部固定创建：`DiffChunker()`、`PromptRenderer()`、`StructuredResponseParser()`。

### 8.2 `run()` 主流程（逐步）

| 步骤 | 代码 | 分支/说明 |
|------|------|-----------|
| 1 | `ctx = context_builder.build(...)` | GitLab 网络/API 错误 → 未捕获则 API Exception fail-open |
| 2 | `chunks = chunker.chunk_files(ctx.changed_files)` | 仅 `is_supported=True` 的文件 |
| 3 | `if not chunks` | `raise NoReviewableChangesError` |
| 4 | 循环 `chunks` | 每块 `_review_chunk` |
| 4a | `_review_chunk` 抛 `LLMReviewError` | 记入 `llm_failures`，**continue**（不中断其它块） |
| 4b | 成功 | 合并 `issues`；`min_score = min(min_score, chunk_score)`；拼接 `summary` |
| 5 | `len(llm_failures) == len(chunks)` | `raise LLMReviewError`（全部失败） |
| 5a | 部分失败 | `summary` 追加 `Partial LLM failures: ...` |
| 6 | `if not REVIEW_DRY_RUN` | `_publish_results` |
| 7 | return dict | `score`, `summary`, `issues`, `code_quality` |

**聚合语义（关键）**

- **分数**：各块 `score` 的 **最小值**（任一块严重问题拉低总分）。
- **issues**：简单 `extend` 合并，**不去重**（去重在 Publisher fingerprint）。
- **summary**：块 summary 用 `" | "` 连接。

### 8.3 `_review_chunk()` 详解

| 阶段 | 操作 |
|------|------|
| System 提示 | `renderer.render_system(context_md=ctx.context_md, language_hint="Java/Spring")` |
| User 摘要 | `_files_summary(chunk["files"])` → markdown 列表 ``- `path` `` |
| Diff 正文 | `_build_diff_text` → `redact_secrets` |
| 分块注记 | `total_chunks > 1` 时追加英文 Note |
| LLM | `messages = [system, user]`；`llm.chat(..., json_mode=True)` |
| 解析 | `parser.parse(raw)`；`ParseError` → 包装为 `LLMReviewError` |

**`_build_diff_text` 单文件格式**

```text
diff --git a/{path} b/{path}
{diff_body}

# Full file: {path}
{content}          # 若 content 非空
```

多块之间用 `\n\n` 连接。

### 8.4 `_publish_results()` 与 `code_quality`

每条 issue 发布 body：

```markdown
**AICR 评审** ({severity}/{category})

{message}

**建议**: {suggestion}   # 仅 suggestion 非空时
```

`_build_code_quality` 将 issue 转为 Code Climate 风格：

```python
{
  "description": message,
  "check_name": "aicr-review",
  "fingerprint": "{file}:{line}:{category}",
  "severity": severity,
  "location": {"path": file, "lines": {"begin": line or 1}},
}
```

---

## 9. 分块器：`DiffChunker`

### 9.1 预算计算

```text
max_chars = REVIEW_MAX_INPUT_TOKENS * 4   # APPROX_CHARS_PER_TOKEN
```

默认 `12000 * 4 = 48000` 字符/块。

### 9.2 `chunk_files` 算法（贪心装箱）

```text
对每个 is_supported 文件 f:
  file_entry = _maybe_truncate_file(f, max_chars)
  file_chars = len(_file_text(file_entry))

  若 current_chars + file_chars > max_chars 且 current_files 非空:
      封存当前 chunk，开启新 chunk

  将 file_entry 加入当前 chunk
```

**注意**：超大单文件先 `_maybe_truncate_file`，仍可能单独占满一块；截断后 `content` 被清空，仅保留截断后的 `diff`。

### 9.3 `_maybe_truncate_file`

当 `len(_file_text(f)) > max_chars`：

- `diff` 截取前 `max_chars` 并追加 `\n... [truncated for token budget]`
- `content` 置 `""`

### 9.4 `_file_text`（计费用文本）

```text
--- {old_path}
+++ {new_path}
{diff}
# Full file content:
{content}
```

---

## 10. 解析器：`StructuredResponseParser`

### 10.1 `parse(raw)` 管道

1. `strip`
2. 若以 `` ``` `` 开头：剥掉 `` ```json `` 与结尾 `` ``` ``
3. `json.loads`；失败 → `_extract_json`
4. `_normalize(data)`

### 10.2 `_extract_json` 正则策略

按顺序尝试模式：

1. `\{[\s\S]*"score"[\s\S]*"issues"[\s\S]*\}`
2. `\{[\s\S]*\}`（最宽）

对每个 match 尝试 `json.loads`，首个成功即返回。

### 10.3 `_normalize` 输出契约

| 字段 | 规则 |
|------|------|
| `score` | `float`，钳制 `[0, 100]` |
| `summary` | `str(data.get("summary", ""))` |
| `issues[]` | 仅保留 `dict` 项；字段默认见下 |

**issue 项默认值**

| 键 | 默认 |
|----|------|
| `file` | `""` |
| `line` | `_safe_line` → `max(0, int(...))`，非法为 0 |
| `severity` | `"info"` |
| `category` | `"other"` |
| `message`, `suggestion` | `""` |

---

## 11. 提示词：`PromptRenderer` 与模板

### 11.1 Jinja2 环境

- 目录：`app/review/prompts/`
- `FileSystemLoader` + `select_autoescape`（字符串模板默认不转义 HTML）

模块级单例 `_env`，模板加载一次。

### 11.2 `system_spring.j2` 结构

1. 角色：`senior code reviewer`，`language_hint` 插值（当前固定 `"Java/Spring"`）
2. 检查维度：Correctness、Spring、Spring Cloud、API、Performance、Configuration
3. 分数档位说明（90–100 … 0–29）
4. **强制 JSON Schema**（score、summary、issues 字段说明）
5. 规则：只报真实问题；每项需 file+line；severity 定义
6. 若 `context_md` 非空：插入 `## Project-Specific Context`

### 11.3 `user_review.j2` 结构

- MR 标题、可选描述
- Changed Files 列表（markdown）
- 代码块包裹 `diff_text`
- 末行：要求 JSON 输出

### 11.4 扩展提示词

- 新增 `system_xxx.j2` 后，在 `PromptRenderer.render_system` 中切换 `get_template` 名或增加参数。
- `language_hint` 仅影响 system 首段描述，**不自动切换检查规则**（规则写在模板内）。

---

## 12. 脱敏：`app/utils/redact.py`

| 模式 | 替换 |
|------|------|
| `(password\|secret\|api_key\|token)\s*[:=]\s*\S+`（忽略大小写） | `\1=***REDACTED***` |
| `glpat-[A-Za-z0-9._-]+` | `glpat-***REDACTED***` |
| `AKIA[0-9A-Z]{16}` | `AKIA***REDACTED***` |

调用点：

- `ContextBuilder.build` → `context_md`
- `ReviewOrchestrator._review_chunk` → `diff_text`（**不**对 system 中的 context_md 二次脱敏，context 已在 build 时脱敏）

---

## 13. CI 门禁脚本：`scripts/ci_review_gate.sh`

**设计原则**：与服务端 fail-open 对称——**只有明确「评审完成且低分」才 `exit 1`**。

```mermaid
flowchart TD
    S[curl POST /review] --> J{jq 可用?}
    J -->|否| P0[pass: jq missing]
    J -->|是| C{curl 成功?}
    C -->|否| P1[pass: request failed]
    C -->|是| H{HTTP 200?}
    H -->|否| P2[pass: HTTP code]
    H -->|是| V{JSON 合法?}
    V -->|否| P3[pass: invalid JSON]
    V -->|是| RC{review_completed == true?}
    RC -->|否| P4[pass: not completed]
    RC -->|是| SC{score 存在?}
    SC -->|否| P5[pass: missing score]
    SC -->|是| T{score < threshold?}
    T -->|是| F[fail_job exit 1]
    T -->|否| P6[pass: score OK]
```

环境变量：

- `AICR_REVIEW_URL`（必需）
- `AICR_REVIEW_SECRET` → `X-AICR-Secret`
- `AICR_SCORE_THRESHOLD`（默认 60）
- `AICR_REVIEW_TIMEOUT`（curl `-m`，默认 300 秒）

---

## 14. 端到端时序（CI 同步路径）

```mermaid
sequenceDiagram
    participant CI as GitLab CI Runner
    participant API as routes.review
    participant OR as ReviewOrchestrator
    participant CB as ContextBuilder
    participant CH as DiffChunker
    participant LLM as OpenAICompatibleProvider
    participant PA as StructuredResponseParser
    participant GP as GitLabPublisher
    participant GL as GitLab

    CI->>API: POST /review + X-AICR-Secret
    API->>OR: run(project_id, mr_iid, diff?)
    OR->>CB: build
    CB->>GL: MR + changes + files.raw + CONTEXT.md
    OR->>CH: chunk_files
    loop 每个 chunk
        OR->>LLM: chat(system, user)
        LLM-->>OR: JSON string
        OR->>PA: parse
    end
    alt REVIEW_DRY_RUN=0
        OR->>GP: publish_issue × N + publish_summary
        GP->>GL: discussions / notes
    end
    OR-->>API: score, issues, summary
    API-->>CI: ReviewResult review_completed=true
    CI->>CI: ci_review_gate.sh 比较 threshold
```

---

## 15. 状态与标志位速查

| 场景 | HTTP | `review_completed` | `score` | GitLab 评论 | CI job |
|------|------|-------------------|---------|-------------|--------|
| 评审成功，分数达标 | 200 | `true` | 实际值 | 已发布（非 dry-run） | 通过 |
| 评审成功，分数低于阈值 | 200 | `true` | 实际值 | 已发布 | **失败** |
| 无可审文件 | 200 | `false` | 100 | 无 | 通过 |
| LLM 全失败 | 200 | `false` | 100 | 无 | 通过 |
| LLM 部分失败 | 200 | `true` | 各块 min | 已发布（基于成功块） | 按分数 |
| 鉴权失败（/review） | 200 | `false` | 100 | 无 | 通过 |
| Webhook 受理 | 200 | N/A（异步） | N/A | 后台可能发布 | N/A |
| `REVIEW_DRY_RUN=1` | 200 | `true`（若成功） | 实际值 | **跳过** | 按分数 |

---

## 16. 冒烟测试覆盖（`scripts/smoke_test.py`）

| 函数 | 验证点 |
|------|--------|
| `test_parser` | 正常 JSON；非法 line；纯文本 → `ParseError` |
| `test_chunker_truncation` | 超大 diff 出现 `[truncated` |
| `test_empty_chunks` | 仅不支持扩展名 → `NoReviewableChangesError` |
| `test_llm_failure_raises` | 全块 LLM 失败 → `LLMReviewError` |
| `test_redact` | 密码与 glpat 被替换 |
| `test_health_import` | `main.app` 可导入 |
| `test_review_fail_open` | `LLMReviewError` → 200 + `review_completed=false` |
| `test_review_auth_fail_open` | 401 鉴权 → fail-open 响应 |

运行：`cd aicr-reviewer && source .venv/bin/activate && python scripts/smoke_test.py`

---

## 17. 常见修改入口（代码级）

| 目标 | 文件 | 函数/常量 |
|------|------|-----------|
| 增加可审语言 | `context_builder.py` | `SUPPORTED_EXTENSIONS` |
| 调整上下文窗口 | `config.py` / `.env` | `REVIEW_MAX_INPUT_TOKENS` |
| 修改分块策略 | `chunker.py` | `chunk_files`, `_maybe_truncate_file` |
| 修改评分聚合 | `orchestrator.py` | `run()` 中 `min_score` 逻辑 |
| 修改 fail-open | `routes.py` | `review()` 的 except 分支 |
| 切换 LLM 厂商 | `.env` | `LLM_PROVIDER`, `LLM_API_BASE` |
| 自定义团队规范 | 业务仓库 | `.llm/CONTEXT.md` |
| 调整评审规则 | `prompts/system_spring.j2` | 模板正文 |
| 行内评论失败行为 | `publisher.py` | `publish_issue`, `_post_inline` |
| CI 阈值 | `.env` + CI 变量 | `AICR_SCORE_THRESHOLD` |

---

## 18. 类型与协议小结

```text
# 核心中间结构
MRContext                    # 一次评审的 GitLab 上下文
changed_files[]: {
  old_path, new_path, diff, content, is_supported
}
chunk: { files: changed_files[], total_chars: int }

# LLM 输出（parser 归一化后）
{
  score: float,
  summary: str,
  issues: [{
    file, line, severity, category, message, suggestion
  }]
}

# API 响应（ReviewResult）
同上 + code_quality[] + review_completed: bool
```

---

## 19. 已知实现细节与陷阱

1. **`ContextBuilder` 未在 `chunk_files` 前过滤 `is_supported=False` 的文件**  
   它们进入 `changed_files` 但不会被分块；若 MR 仅有 `.md` 等变更，`chunks` 为空 → `NoReviewableChangesError`。

2. **Webhook 与 CI 的 fail-open 不对称**  
   Webhook 鉴权失败返回 401；CI `/review` 鉴权失败仍 200 fail-open。

3. **部分 LLM 块失败仍可能 `review_completed=true`**  
   CI 可能按偏低 `min_score` 拦 MR，即使 summary 含 `Partial LLM failures`。

4. **`Publisher._seen` 不跨 MR 持久**  
   每次 `run()` 新建 Publisher；同一 MR 多次评审可能重复相似评论（fingerprint 仅批次内）。

5. **`language_hint` 写死**  
   `orchestrator._review_chunk` 固定 `"Java/Spring"`；非 Java 项目需改代码或模板。

6. **单例 GitLab 客户端**  
   修改 `GITLAB_URL`/token 后需重启进程才生效。

---

## 20. 文件索引（函数级）

| 文件 | 主要符号 |
|------|----------|
| `main.py` | `app` |
| `app/config.py` | `_load_env_files`, 各常量 |
| `app/exceptions.py` | `ReviewError`, `LLMReviewError`, `NoReviewableChangesError` |
| `app/api/routes.py` | `review`, `gitlab_webhook`, `health`, `_fail_open_review`, `_verify_review_auth`, `_run_orchestrator` |
| `app/gitlab/client.py` | `get_gitlab_client` |
| `app/gitlab/context_builder.py` | `MRContext`, `ContextBuilder.build`, `_load_context_md`, `_default_context` |
| `app/gitlab/publisher.py` | `GitLabPublisher.publish_issue`, `publish_summary`, `_post_inline`, `_post_note` |
| `app/llm/factory.py` | `create_llm_provider`, `_PROVIDER_MAP` |
| `app/llm/openai_compat.py` | `OpenAICompatibleProvider.chat`, `_complete`, `_json_mode_unsupported` |
| `app/review/orchestrator.py` | `ReviewOrchestrator.run`, `_review_chunk`, `_publish_results`, `_build_code_quality` |
| `app/review/chunker.py` | `DiffChunker.chunk_files`, `_maybe_truncate_file`, `_file_text` |
| `app/review/parser.py` | `StructuredResponseParser.parse`, `ParseError` |
| `app/review/prompt_renderer.py` | `PromptRenderer.render_system`, `render_user` |
| `app/utils/redact.py` | `redact_secrets` |
| `scripts/ci_review_gate.sh` | `pass_job`, `fail_job` |
| `scripts/smoke_test.py` | `test_*` |

---

*文档版本与代码同步至仓库 `aicr-reviewer` 应用 `2.0.0`；若实现变更请优先对照源码更新本节。*

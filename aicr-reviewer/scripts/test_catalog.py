"""L1/L2 测试用例中文说明（报告落盘用）。"""

from __future__ import annotations

# name -> (category_zh, description_zh)
SMOKE_TEST_ZH: dict[str, tuple[str, str]] = {
    "test_parser": ("解析与分块", "合法 JSON 解析；非法 line 归零；纯文本抛 ParseError"),
    "test_parser_markdown_fence": ("解析与分块", "Markdown ```json 代码块包裹的 LLM 响应"),
    "test_parser_score_clamp": ("解析与分块", "score 限制在 0–100"),
    "test_parser_embedded_json": ("解析与分块", "从前后缀噪声中提取 JSON"),
    "test_parser_skips_non_dict_issues": ("解析与分块", "issues 中非 dict 项被跳过"),
    "test_chunker_truncation": ("解析与分块", "单文件超大 diff 出现截断标记"),
    "test_chunker_splits_chunks": ("解析与分块", "多文件按 token 预算拆成多块"),
    "test_chunker_skips_unsupported": ("解析与分块", "不支持扩展名的文件不入块"),
    "test_chunker_single_tokenize_per_file": ("解析与分块", "单文件只 tokenize 一次"),
    "test_empty_chunks": ("评审流水线", "无可评审文件时抛 NoReviewableChangesError"),
    "test_llm_failure_raises": ("评审流水线", "全部 chunk LLM 失败时抛 LLMReviewError"),
    "test_partial_chunk_incomplete": ("评审流水线", "部分 chunk 失败 → review_completed=false"),
    "test_orchestrator_success": ("评审流水线", "Mock LLM 成功 → 聚合 score/issues"),
    "test_orchestrator_filters_out_of_diff": ("评审流水线", "diff hunk 外的 issue 被过滤"),
    "test_orchestrator_skip_unchanged_sha": ("评审流水线", "head SHA 未变时跳过 LLM，仍返回 system_template/prompt_sha256"),
    "test_orchestrator_parallel_chunks": ("评审流水线", "多块 MR 并行调用 LLM"),
    "test_orchestrator_deletions_only": ("评审流水线", "仅删除变更合成评审块"),
    "test_diff_compress_deletion_only_hunk": ("评审流水线", "diff 压缩：deletion-only hunk"),
    "test_diff_compress_deletion_only_lines": ("评审流水线", "diff 压缩：删行合并"),
    "test_diff_compress_entire_file_delete": ("评审流水线", "diff 压缩：整文件删除列表"),
    "test_language_priority_sort": ("评审流水线", "按扩展名频率对变更文件排序"),
    "test_review_state_store": ("评审流水线", "last_reviewed_sha 增量状态持久化"),
    "test_token_utils_fallback": ("评审流水线", "关闭 tiktoken 时用字符÷4 估算"),
    "test_should_fetch_full_file": ("评审流水线", "增量评审是否拉取源分支全文"),
    "test_diff_line_index": ("评审流水线", "diff hunk 行号索引构建"),
    "test_reconcile_score_after_filter": ("评审流水线", "过滤 issue 后分数 reconcile"),
    "test_should_reflect": ("评审流水线", "self-reflection 触发条件"),
    "test_should_reflect_all_issues_filtered": ("评审流水线", "issue 全被过滤时的 reflection 逻辑"),
    "test_reflection_includes_diff_text": ("评审流水线", "reflection 提示词包含 diff 文本"),
    "test_resolve_system_template": ("提示词", "按 language_hint 选择 system 模板"),
    "test_prompt_renderer_multilang": ("提示词", "多语言 system 模板渲染含 score 字段"),
    "test_prompt_variant_override": ("提示词", "variants 变体模板覆盖渲染"),
    "test_prompt_variant_disallowed_path": ("提示词", "拒绝含 .. 的非白名单模板路径"),
    "test_render_system_text_compat": ("提示词", "render_system_text 兼容包装仅返回文本"),
    "test_resolve_effective_template_strict": ("提示词", "无效 template 在 strict 模式下抛错"),
    "test_review_invalid_system_template_400": ("HTTP API", "非法 system_template 返回 400"),
    "test_review_system_template_applied": ("HTTP API", "响应含 applied/requested 模板字段"),
    "test_prompt_untrusted_metadata": ("安全", "MR 元数据防注入 XML 边界"),
    "test_paths_match_strict": ("评审流水线", "diff 过滤严格路径匹配"),
    "test_filter_deleted_paths_allowed": ("评审流水线", "已删除文件路径允许匹配 issue"),
    "test_redact": ("安全", "password=、glpat- 等密钥脱敏"),
    "test_redact_aws_key": ("安全", "AWS AKIA 样式密钥脱敏"),
    "test_supported_extensions": ("安全", "可评审扩展名判定"),
    "test_redact_mr_metadata": ("安全", "MR 标题/描述/extra_diff 脱敏"),
    "test_health_import": ("HTTP API", "FastAPI 应用可导入"),
    "test_health_minimal": ("HTTP API", "GET /health 返回 status=ok"),
    "test_health_detail": ("HTTP API", "GET /health/detail 含配置探测字段"),
    "test_review_fail_open": ("HTTP API", "LLM 异常时 fail-open：review_completed=false"),
    "test_review_no_reviewable_changes": ("HTTP API", "无可评审变更时占位分且未完成"),
    "test_review_auth_returns_401": ("HTTP API", "评审 API 错误密钥返回 401"),
    "test_review_bearer_auth_ok": ("HTTP API", "Authorization Bearer 鉴权通过"),
    "test_review_secret_not_configured": ("HTTP API", "未配置 secret 且未允许不安全 → 503"),
    "test_review_concurrency_503": ("HTTP API", "并发槽位满返回 503"),
    "test_mr_review_lock": ("HTTP API", "同一 MR 并发评审锁"),
    "test_review_mr_busy_409": ("HTTP API", "同一 MR 重复评审返回 409"),
    "test_webhook_ignored": ("HTTP API", "非 MR Webhook 事件被忽略"),
    "test_webhook_unauthorized": ("HTTP API", "Webhook 密钥错误返回 401"),
    "test_webhook_accepted": ("HTTP API", "合法 MR open 事件返回 accepted"),
    "test_webhook_review_suppressed": ("HTTP API", "describe 后短时抑制 webhook 全量 review"),
    "test_config_toml_merge": ("阶段 C", "部署 config.toml 与 env 合并"),
    "test_should_respond_to_note": ("阶段 C", "Note 评论触发词识别"),
    "test_tool_parser_describe": ("阶段 C", "describe 工具 JSON 解析"),
    "test_describe_prompt_untrusted": ("阶段 C", "describe 模板防注入"),
    "test_webhook_note_ignored": ("阶段 C", "无关 Note 事件被忽略"),
    "test_webhook_note_accepted": ("阶段 C", "合法 Note 问答事件 accepted"),
    "test_note_ask_background_calls_run_ask": ("阶段 C", "Note 后台异步 ask"),
    "test_webhook_note_update_ignored": ("阶段 C", "Note update 事件被忽略"),
    "test_describe_disabled_503": ("阶段 C", "describe 关闭时返回 503"),
    "test_diff_text_truncation": ("阶段 C", "工具侧 diff 文本截断"),
    "test_llm_settings_for_tool": ("阶段 C", "按工具读取 LLM 配置"),
    "test_create_llm_for_tool": ("阶段 C", "按工具创建 LLM Provider"),
    "test_tool_parser_changelog_ask": ("阶段 C", "changelog/ask 工具 JSON 解析"),
    "test_extract_user_question": ("阶段 C", "从 Note 提取用户提问"),
    "test_changelog_upsert_note": ("阶段 C", "CHANGELOG note 去重更新"),
    "test_describe_tool_mock": ("阶段 C", "describe 写回 MR 并抑制 webhook"),
    "test_llm_factory_missing_key": ("LLM", "未配置 LLM_API_KEY 时工厂抛错"),
    "test_prompt_matrix_template_ok": ("L3 矩阵", "template_ok 判定 503/fail-open/成功"),
    "test_prompt_matrix_exit_code": ("L3 矩阵", "prompt_matrix_test 矩阵失败 exit 1、全通过 exit 0"),
    "test_validate_scenario": ("L3 验收", "validate_scenario 分数/关键词/文件命中"),
    "test_assert_gitlab_publish": ("L3 验收", "assert_gitlab_publish AICR note 识别"),
    "test_acceptance_timing": ("L3 验收", "acceptance_timing 耗时格式化与 timing.json"),
    "test_l3_full_preflight": ("L3 验收", "L3-full preflight 占位符与中止 summary"),
}

L1_REPORT_TITLE_ZH = "L1 冒烟测试报告"
L2_REPORT_TITLE_ZH = "L2 服务健康检查报告"

HEALTH_CHECK_ZH: dict[str, dict[str, str]] = {
    "/health": {
        "name_zh": "基础健康检查",
        "description_zh": "确认 AICR 进程存活，返回 {\"status\":\"ok\"}",
    },
    "/health/detail": {
        "name_zh": "配置探测",
        "description_zh": "检查 GitLab URL、token/LLM 密钥是否已配置、并发与功能开关",
    },
}

DETAIL_FIELD_ZH: dict[str, str] = {
    "gitlab_url": "GitLab 地址",
    "token_set": "GitLab Bot Token 已配置",
    "llm_provider": "LLM 提供商",
    "llm_model": "LLM 模型",
    "llm_key_set": "LLM API Key 已配置",
    "review_auth_required": "评审 API 需要密钥",
    "review_api_allow_insecure": "允许无密钥评审（仅本地）",
    "review_dry_run": "评审 dry-run（不写入 GitLab）",
    "review_max_concurrent": "最大并发评审数",
    "incremental_review": "增量评审已启用",
    "describe_enabled": "describe 工具已启用",
    "changelog_enabled": "changelog 工具已启用",
    "ask_enabled": "评论问答已启用",
    "webhook_note_enabled": "Note Webhook 已启用",
}


def smoke_entry_zh(name: str) -> dict[str, str]:
    cat, desc = SMOKE_TEST_ZH.get(name, ("其它", "（暂无中文说明）"))
    return {"category_zh": cat, "description_zh": desc, "name_zh": desc.split("；")[0].split("→")[0]}


def status_zh(status: str) -> str:
    return {"passed": "通过", "failed": "失败"}.get(status, status)

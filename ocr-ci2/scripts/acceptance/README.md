# 验收 / 构建辅助脚本（非 Gateway 运行时）

| 脚本 | 用途 |
|------|------|
| `bake_ocr_config.py` | 构建镜像时将 `--config` / 用户 config **原样**写入 `.build/config.json`（无 defaults 合并） |
| `verify_gateway_runner.ps1` | E2E 跑前检查（GitLab + Runner + Gateway） |
| `create_or_update_mr.py` | 创建或查找 GitLab MR |
| `env_loader.py` | 共享 `.env` / token 加载（实现位于 `scripts/env_loader.py`） |
| `print_gitlab_token.py` | 输出 GitLab token（供 verify 脚本与 shell 复用） |

运行时脚本见 `scripts/post_ocr_to_gitlab.py` 等。  
E2E 联调见 [docs/测试与验收.md](../../docs/测试与验收.md)。

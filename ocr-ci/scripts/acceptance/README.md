# 验收 / 构建辅助脚本（非 CI Job 运行时）

与 `scripts/` 根目录下的**部署与运行时**脚本区分：

| 脚本 | 用途 |
|------|------|
| `bake_ocr_config.py` | **构建镜像**时将 `--config` / 用户 config **原样**写入 `.build/config.json`（无 defaults 合并）；**不是**自动化测试。Gateway 生产请用 `ocr-ci2/`。 |
| `verify_local_ocr.py` | 本机验收：OCR CLI、config、GitLab API、`ocr review`（不替代 Pipeline）。 |

运行时（MR 发帖、Gateway）使用 `scripts/post_ocr_to_gitlab.py`、`scripts/gitlab_mr.py`、`scripts/ocr_ci_config.py`。

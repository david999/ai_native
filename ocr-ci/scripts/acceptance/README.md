# 验收 / 构建辅助脚本（非 CI Job 运行时）

与 `scripts/` 根目录下的**部署与运行时**脚本区分：

| 脚本 | 用途 |
|------|------|
| `bake_ocr_config.py` | **构建镜像**时，将你本机 `~/.opencodereview/config.json` 合并进 `.build/config.json` 再 COPY 进镜像；**不是**自动化测试。OCR 配置仍由你在用户目录自管，`build_image.ps1` 默认读取该文件。 |
| `verify_local_ocr.py` | 本机验收：OCR CLI、config、GitLab API、`ocr review`（不替代 Pipeline）。 |

运行时（MR 发帖、Gateway）使用 `scripts/post_ocr_to_gitlab.py`、`scripts/gitlab_mr.py`、`scripts/ocr_ci_config.py`。

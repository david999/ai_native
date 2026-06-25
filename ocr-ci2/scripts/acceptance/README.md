# 验收 / 构建辅助脚本（非 Gateway 运行时）

| 脚本 | 用途 |
|------|------|
| `bake_ocr_config.py` | 构建 `ocr-gateway:local` 时从 `~/.opencodereview/config.json` 生成 `.build/config.json`（非自动化测试）。 |
| `verify_local_ocr.py` | 可选：从 ocr-ci 复制或共用本机验收流程。 |

运行时脚本见 `scripts/post_ocr_to_gitlab.py` 等。

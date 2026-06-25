# 验收 / 构建辅助脚本（非 Gateway 运行时）

| 脚本 | 用途 |
|------|------|
| `bake_ocr_config.py` | 构建 Docker 镜像时从 `~/.opencodereview/config.json` 生成 `.build/config.json` |

运行时脚本见 `scripts/post_ocr_to_gitlab.py` 等。  
E2E 联调见 [docs/测试与验收.md](../../docs/测试与验收.md)。

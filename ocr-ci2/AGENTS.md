# OCR Gateway（ocr-ci2）— AI 编码指引

本子项目位于 monorepo 的 `ocr-ci2/`，**部署与运行时文档以本目录为准**。

## 项目边界

| 范围 | 说明 |
|------|------|
| 改代码 | 优先只动 `ocr-ci2/` 内文件 |
| 部署文档 | `docs/本地部署指南.md`、`docs/生产部署指南.md`、`docs/架构说明.md` — **禁止**引用 `../test_data`、`../evn`、`../ocr-ci` |
| 测试文档 | `docs/测试与验收.md` — **可**引用 monorepo 路径（datacalc-web、verify 脚本等），并同步 [test_data/README.md](../test_data/README.md) 相关小节 |

## 文档同步

| 改了什么 | 更新什么 |
|----------|----------|
| `gateway/*` | `docs/架构说明.md`、`docs/本地部署指南.md`、`docs/生产部署指南.md` |
| `deploy/local/*`、`deploy/prod/ci/snippet.native-host.yml` | `docs/本地部署指南.md` |
| `deploy/prod/native/*`、`deploy/prod/docker/*`、`snippet.docker.yml` | `docs/生产部署指南.md`、`docs/生产环境运维部署手册.md` |
| 集成 / E2E 行为 | `docs/测试与验收.md` |
| 任意用户可见行为 | `README.md`、`docs/文档索引.md` |

不要求修改 monorepo 根 `docs/` 正文；根 [docs/文档索引.md](../docs/文档索引.md) 仅保留 ocr-ci2 入口链接。

## 验收

```powershell
cd ocr-ci2
pip install -r requirements-dev.txt
pytest
```

- 单元测试：上述命令（默认）
- E2E 联调：见 [docs/测试与验收.md](docs/测试与验收.md)

## 快速路径

| 任务 | 入口 |
|------|------|
| 本地启动 Gateway | `deploy/local/run.ps1` |
| 业务仓 CI 片段 | `deploy/prod/ci/snippet.native-host.yml` |
| 文档索引 | [docs/文档索引.md](docs/文档索引.md) |

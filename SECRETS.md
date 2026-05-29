# Local Credential Management

This repository uses a single `.env` file (git-ignored) to centralize all local development tokens and secrets.

## Rules

1. Never commit `.env` or any file containing real token values.
2. Do not paste tokens into chat logs, issues, or code comments.
3. Prefer short-lived tokens when possible; for local dev, long expiry or no expiry is acceptable.
4. Rotate tokens at least every 6-12 months or when a team member leaves.
5. Use the minimum scopes required for each token (principle of least privilege).

## Current Tokens (local only)

- **AICR_BOT_TOKEN**  
  Used by: `aicr-reviewer` container + CI review jobs  
  Purpose: Read MR diffs + post line-specific discussion comments on MRs  
  Required scopes: `api` (or at minimum `read_api` + `write_repository` for comments)  
  Current level: Developer (30) in java_group (sufficient for this use case)

- **ROOT_PAT** (to be created)  
  Used by: Initial setup, project/group administration, emergency recovery  
  Required scopes: `api` (full)  
  Created from the one-time root password via GitLab UI.

## How to Add a New Token

1. Create the token in GitLab (User Settings > Access Tokens or Group/Project settings).
2. Add a new line in `.env`:
   ```
   MY_NEW_SERVICE_TOKEN=glpat-...
   ```
3. Reference it in `docker-compose.yml` or scripts via environment variable.
4. Document the purpose and required scopes in this file.

## Root Password Handling

The plain root password (`jkalF0jkd&*W34SD`) was used **only once** to log into the UI and generate `ROOT_PAT`.

After successful PAT creation:
- Remove or comment out any local notes containing the plain password.
- The PAT in `.env` is the only long-term credential needed.

## Recovery

If a token is lost or compromised:
1. Revoke it immediately in GitLab UI.
2. Generate a replacement.
3. Update `.env` and restart affected services (`docker compose restart`).

## LLM API Key（天翼云 / DeepSeek / 智谱）

- **LLM_API_KEY**
  Used by: `aicr-reviewer` container only (never exposed to CI jobs)
  Purpose: Authenticate with LLM provider for code review
  获取路径: 天翼云 → 一站式智算平台 → 模型服务 → 服务接入 → 创建服务组 → AppKey
  安全要求:
  - 禁止写入代码、提交仓库或放入 `.gitlab-ci.yml`
  - 仅通过 `.env` + `docker-compose.yml` 的 `env_file` 注入容器
  - 日志禁止打印 `Authorization` 头
  - 泄露后立即在天翼云控制台作废 → 更新 `.env` → `docker compose restart aicr-reviewer`

- **LLM_PROVIDER**: `ctyun_openai` | `deepseek` | `zhipu` | `openai`
- **LLM_API_BASE**: 对应端点 URL（切换 provider 时自动适配 preset）
- **LLM_MODEL**: 模型 ID（天翼云为控制台分配的 model_id 字符串）

## 运行方式

| 环境 | Reviewer 启动 | GitLab URL |
|------|---------------|------------|
| 本地开发（无 Docker） | `aicr-reviewer/scripts/run_local.ps1` | `http://localhost:8000` |
| Linux 生产（Docker） | `deploy/docker-compose.aicr-reviewer.yml` | 容器内 `http://gitlab:8000` |

## AICR CI 行为（非密钥）

- **评审超时 / 服务不可用**：在 `spring-cloud-demo/.gitlab-ci.yml` 的 `AICR_REVIEW_TIMEOUT_SECONDS`（或 GitLab 项目 CI/CD Variables）配置；超时后 `review` job **通过**，不阻断合并。
- **低分阻断合并**：由 `AICR_SCORE_THRESHOLD` 控制，仅 review 成功返回且分数低于阈值时 pipeline 失败。
- **CI 不持有 LLM 密钥**：CI job 仅调用内网 `aicr-reviewer` 服务，LLM API Key 只在 reviewer 进程/容器内。
- **本地无 Docker**：在 `aicr-reviewer` 目录执行 `scripts/run_local.ps1`，`.env` 中 `GITLAB_URL=http://localhost:8000`。

## References

- GitLab Personal Access Tokens: https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html
- Minimum permissions for Merge Request discussions: Developer (30) or higher on the project/group.

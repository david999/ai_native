#!/usr/bin/env python3
"""L3-full 跑前自动检查：能自动处理的由脚本完成，仅缺密钥/需人工安装时退出并提示。"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AICR_ROOT = REPO_ROOT / "aicr-reviewer"
ENV_DIR = REPO_ROOT / "evn"
ENV_FILE = ENV_DIR / ".env"
ENV_EXAMPLE = ENV_DIR / ".env.example"
RUN_LOG_TEMPLATE = REPO_ROOT / "docs" / "templates" / "l3-full-run-log.md"
AICR_HEALTH_DETAIL = "http://localhost:8001/health/detail"

_PLACEHOLDER_RE = re.compile(r"(\.\.\.|xxxx|your[-_]?|changeme|replace[-_]?me|todo|placeholder)", re.I)


def _read_env_file(path: Path | None = None) -> dict[str, str]:
    path = path or ENV_FILE
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        out[k.strip()] = v.strip()
    return out


def _env_get(name: str, file_vars: dict[str, str]) -> str:
    if str(AICR_ROOT) not in sys.path:
        sys.path.insert(0, str(AICR_ROOT))
    from app.env_loader import os_env_first

    val = os_env_first(name)
    if val:
        return val
    return (file_vars.get(name) or "").strip()


def _truthy(val: str) -> bool:
    return val.strip().lower() in ("1", "true", "yes", "on")


def _is_placeholder_secret(name: str, value: str, example_vars: dict[str, str]) -> bool:
    if not value:
        return True
    if _PLACEHOLDER_RE.search(value):
        return True
    ex = (example_vars.get(name) or "").strip()
    if ex and value == ex:
        return True
    if name in ("AICR_BOT_TOKEN", "ROOT_PAT", "LLM_API_KEY") and value.endswith("..."):
        return True
    return False


def _http_json(url: str, timeout: float = 5.0) -> tuple[bool, dict | str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = resp.read().decode()
            if 200 <= resp.status < 300:
                try:
                    return True, json.loads(body)
                except json.JSONDecodeError:
                    return True, body
            return False, f"HTTP {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except OSError as e:
        return False, str(e)


def _run_ps1(script: Path, *extra: str) -> tuple[int, str]:
    if not script.is_file():
        return 1, f"missing script: {script}"
    cmd = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *extra,
    ]
    r = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    return r.returncode, out.strip()[-2000:]


def write_abort_artifacts(
    record_dir: Path,
    *,
    level: str = "L3-full",
    reason: str,
    preflight: dict | None = None,
) -> None:
    record_dir = Path(record_dir)
    record_dir.mkdir(parents=True, exist_ok=True)
    finished = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    summary = {
        "level": level,
        "record_dir": str(record_dir),
        "failed": True,
        "aborted": True,
        "abort_reason": reason,
        "l3_skipped": True,
        "finished": finished,
    }
    if preflight:
        summary["preflight"] = {
            "ok": preflight.get("ok"),
            "user_actions": preflight.get("user_actions") or [],
        }
    (record_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_preflight(*, record_dir: Path | None = None, skip_infra: bool = False) -> dict:
    checks: list[dict] = []
    user_actions: list[str] = []
    file_vars = _read_env_file()
    example_vars = _read_env_file(ENV_EXAMPLE)
    infra_ready = False

    # evn/.env
    if not ENV_FILE.is_file():
        if ENV_EXAMPLE.is_file():
            shutil.copy2(ENV_EXAMPLE, ENV_FILE)
            file_vars = _read_env_file()
            checks.append(
                {
                    "id": "env_file",
                    "ok": False,
                    "auto_fixed": True,
                    "detail": "已从 evn/.env.example 复制 evn/.env",
                    "user_action": "请编辑 evn/.env 填入 AICR_BOT_TOKEN、LLM_API_KEY 等后重跑",
                }
            )
            user_actions.append("编辑 evn/.env：填入 AICR_BOT_TOKEN、LLM_API_KEY、LLM_MODEL")
        else:
            checks.append(
                {
                    "id": "env_file",
                    "ok": False,
                    "detail": "缺少 evn/.env 与 evn/.env.example",
                    "user_action": "创建 evn/.env 并配置密钥",
                }
            )
            user_actions.append("创建 evn/.env 并配置密钥")
    else:
        checks.append({"id": "env_file", "ok": True, "detail": str(ENV_FILE)})

    def require_secret(name: str, hint: str) -> None:
        val = _env_get(name, file_vars)
        ok = bool(val) and not _is_placeholder_secret(name, val, example_vars)
        entry: dict = {
            "id": name,
            "ok": ok,
            "detail": "set" if ok else ("placeholder or missing" if val else "missing or empty"),
        }
        if not ok:
            entry["user_action"] = hint
            user_actions.append(hint)
        checks.append(entry)

    require_secret(
        "AICR_BOT_TOKEN",
        "在 evn/.env 或系统环境变量中设置有效的 GitLab Bot PAT（非 glpat-... 占位符）",
    )
    require_secret("LLM_API_KEY", "设置有效的 LLM_API_KEY（非空、非占位符）")
    require_secret("LLM_MODEL", "设置有效的 LLM_MODEL（非空、非占位符）")

    dry = _env_get("REVIEW_DRY_RUN", file_vars) or "0"
    dry_ok = not _truthy(dry)
    checks.append(
        {
            "id": "REVIEW_DRY_RUN",
            "ok": dry_ok,
            "detail": f"REVIEW_DRY_RUN={dry} (env file)",
            **(
                {"user_action": "L3-full 须 REVIEW_DRY_RUN=0（真实 GitLab 发帖）；改 evn/.env 后重启 AICR"}
                if not dry_ok
                else {}
            ),
        }
    )
    if not dry_ok:
        user_actions.append("设置 REVIEW_DRY_RUN=0 并重启 AICR")

    # 运行中 AICR 进程的 REVIEW_DRY_RUN（与 env 文件可能不一致）
    aicr_ok, aicr_body = _http_json(AICR_HEALTH_DETAIL)
    if aicr_ok and isinstance(aicr_body, dict):
        runtime_dry = bool(aicr_body.get("review_dry_run"))
        runtime_ok = not runtime_dry
        checks.append(
            {
                "id": "aicr_review_dry_run",
                "ok": runtime_ok,
                "detail": f"running AICR review_dry_run={runtime_dry}",
                **(
                    {
                        "user_action": "当前 AICR 进程仍为 dry-run；设置 REVIEW_DRY_RUN=0 后重启 AICR（./scripts/run_local.sh）"
                    }
                    if not runtime_ok
                    else {}
                ),
            }
        )
        if not runtime_ok:
            user_actions.append("重启 AICR：REVIEW_DRY_RUN=0")
    else:
        checks.append(
            {
                "id": "aicr_health",
                "ok": False,
                "detail": str(aicr_body),
                "user_action": "启动 AICR：cd aicr-reviewer && ./scripts/run_local.sh",
            }
        )
        user_actions.append("启动 AICR 服务（http://localhost:8001）")

    insecure = _env_get("REVIEW_API_ALLOW_INSECURE", file_vars)
    secret = _env_get("REVIEW_API_SECRET", file_vars)
    auth_ok = _truthy(insecure) or bool(secret)
    checks.append(
        {
            "id": "review_auth",
            "ok": auth_ok,
            "detail": "REVIEW_API_ALLOW_INSECURE=1" if _truthy(insecure) else ("secret set" if secret else "none"),
            **(
                {"user_action": "设置 REVIEW_API_ALLOW_INSECURE=1 或 REVIEW_API_SECRET（/review 鉴权）"}
                if not auth_ok
                else {}
            ),
        }
    )
    if not auth_ok:
        user_actions.append("配置 /review 鉴权：REVIEW_API_ALLOW_INSECURE=1 或 REVIEW_API_SECRET")

    gitlab_url = _env_get("GITLAB_URL", file_vars) or "http://localhost:8000"
    checks.append({"id": "GITLAB_URL", "ok": True, "detail": gitlab_url})

    # venv
    venv_py = AICR_ROOT / ".venv" / ("Scripts" if sys.platform == "win32" else "bin") / "python"
    venv_ok = venv_py.is_file()
    checks.append(
        {
            "id": "venv",
            "ok": venv_ok,
            "auto_fixed": False,
            "detail": str(venv_py) if venv_ok else "missing",
            **(
                {
                    "user_action": "首次运行由 run_acceptance 自动创建 .venv；若失败请手动: python -m venv .venv && pip install -r requirements.txt"
                }
                if not venv_ok
                else {}
            ),
        }
    )

    # run-log template copy
    if record_dir:
        record_dir = Path(record_dir)
        record_dir.mkdir(parents=True, exist_ok=True)
        dest = record_dir / "run-log.md"
        if RUN_LOG_TEMPLATE.is_file() and not dest.is_file():
            shutil.copy2(RUN_LOG_TEMPLATE, dest)
            checks.append(
                {"id": "run_log", "ok": True, "auto_fixed": True, "detail": str(dest)}
            )
        elif dest.is_file():
            checks.append({"id": "run_log", "ok": True, "detail": str(dest)})
        else:
            checks.append(
                {
                    "id": "run_log",
                    "ok": False,
                    "detail": f"template missing: {RUN_LOG_TEMPLATE}",
                }
            )

    # 基础设施：Rancher + GitLab（可自动拉起）
    if not skip_infra and not user_actions:
        rancher_ok = False
        gitlab_ok = False
        if sys.platform == "win32":
            rancher_ps1 = REPO_ROOT / "test_data" / "scripts" / "ensure_rancher.ps1"
            rc, tail = _run_ps1(rancher_ps1)
            rancher_ok = rc == 0
            checks.append(
                {
                    "id": "rancher",
                    "ok": rancher_ok,
                    "detail": tail[-500:] if tail else f"exit {rc}",
                    **(
                        {
                            "user_action": "安装并启动 Rancher Desktop（Container Engine = dockerd/moby），然后重跑"
                        }
                        if not rancher_ok
                        else {}
                    ),
                }
            )
            if not rancher_ok:
                user_actions.append("安装/启动 Rancher Desktop（moby 引擎）")

            gitlab_ps1 = REPO_ROOT / "test_data" / "scripts" / "ensure_gitlab.ps1"
            rc2, tail2 = _run_ps1(gitlab_ps1)
            gitlab_ok = rc2 == 0
            checks.append(
                {
                    "id": "gitlab",
                    "ok": gitlab_ok,
                    "detail": tail2[-500:] if tail2 else f"exit {rc2}",
                    **(
                        {
                            "user_action": f"GitLab 无法在 {gitlab_url} 就绪；检查 Rancher、evn/gitlab compose，或手动运行 ensure_gitlab.ps1"
                        }
                        if not gitlab_ok
                        else {}
                    ),
                }
            )
            if not gitlab_ok:
                user_actions.append(f"修复 GitLab（{gitlab_url} 不可达）")
        else:
            for sid, script in (
                ("rancher", REPO_ROOT / "test_data" / "scripts" / "ensure_rancher.sh"),
                ("gitlab", REPO_ROOT / "test_data" / "scripts" / "ensure_gitlab.sh"),
            ):
                if script.is_file():
                    r = subprocess.run(["bash", str(script)], cwd=str(REPO_ROOT), capture_output=True, text=True)
                    ok = r.returncode == 0
                    checks.append({"id": sid, "ok": ok, "detail": (r.stdout or r.stderr)[-500:]})
                    if sid == "rancher":
                        rancher_ok = ok
                    if sid == "gitlab":
                        gitlab_ok = ok
                    if not ok:
                        user_actions.append(f"修复 {sid}（见脚本输出）")
                elif sid == "gitlab":
                    ready, msg = _http_json(gitlab_url.rstrip("/") + "/")
                    gitlab_ok = ready
                    checks.append({"id": "gitlab", "ok": ready, "detail": str(msg)})
        infra_ready = rancher_ok and gitlab_ok

    user_actions = list(dict.fromkeys(user_actions))
    ok = all(c.get("ok") for c in checks) and not user_actions
    return {
        "ok": ok,
        "checks": checks,
        "user_actions": user_actions,
        "infra_ready": infra_ready,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="L3-full preflight checks")
    ap.add_argument("--record-dir", default="")
    ap.add_argument("--report-json", default="")
    ap.add_argument("--skip-infra", action="store_true", help="Skip Rancher/GitLab auto-start")
    args = ap.parse_args()

    if str(AICR_ROOT) not in sys.path:
        sys.path.insert(0, str(AICR_ROOT))
    from app.env_loader import apply_monorepo_env

    apply_monorepo_env()

    record = Path(args.record_dir) if args.record_dir else None
    result = run_preflight(record_dir=record, skip_infra=args.skip_infra)

    if args.report_json:
        Path(args.report_json).write_text(
            json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    print("=== L3-full 跑前检查 ===")
    for c in result["checks"]:
        mark = "OK" if c.get("ok") else "FAIL"
        fix = " (已自动处理)" if c.get("auto_fixed") else ""
        print(f"  [{mark}] {c['id']}: {c.get('detail', '')}{fix}")

    if result["user_actions"]:
        print("")
        print(">>> 需要您处理（完成后重新运行 L3-full）：")
        for i, action in enumerate(result["user_actions"], 1):
            print(f"  {i}. {action}")
        if record:
            write_abort_artifacts(
                record,
                reason="preflight failed",
                preflight=result,
            )
        return 1

    print("")
    print("跑前检查全部通过，继续验收...")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

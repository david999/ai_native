# L3b 跑前校验：GitLab + Runner 容器 + 网络可达 AICR
param(
    [string]$GitLabUrl = "http://localhost:8000",
    [string]$AicrUrl = "http://localhost:8001",
    [switch]$Json
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$GitLabDir = Join-Path $RepoRoot "evn\gitlab"
$RunnerConfig = Join-Path $RepoRoot "evn\gitlab-runner\config\config.toml"

function Add-RancherDockerToPath {
    $bin = if ($env:RANCHER_DOCKER_BIN) { $env:RANCHER_DOCKER_BIN } else { Join-Path $env:USERPROFILE ".rd\bin" }
    if (Test-Path $bin) { $env:PATH = "$bin;$env:PATH" }
}

Add-RancherDockerToPath

$checks = [System.Collections.Generic.List[object]]::new()
function Add-Check {
    param([string]$Id, [bool]$Ok, [string]$Detail, [string]$Fix = "")
    $checks.Add([pscustomobject]@{ id = $Id; ok = $Ok; detail = $Detail; fix = $Fix })
}

# GitLab
try {
    $r = Invoke-WebRequest -Uri $GitLabUrl -UseBasicParsing -TimeoutSec 10 -MaximumRedirection 0 -ErrorAction SilentlyContinue
    $ok = $r.StatusCode -in 200, 302, 301
    Add-Check "gitlab" $ok "HTTP $($r.StatusCode) $GitLabUrl"
} catch {
    if ($_.Exception.Response.StatusCode.value__ -in 302, 301) {
        Add-Check "gitlab" $true "HTTP redirect $GitLabUrl (GitLab up)"
    } else {
        Add-Check "gitlab" $false $_.Exception.Message "cd evn/gitlab; .\start.ps1"
    }
}

# GitLab container
$gitlabPs = docker ps --filter "name=^gitlab$" --format "{{.Status}}" 2>$null
Add-Check "gitlab_container" ([bool]$gitlabPs) ($(if ($gitlabPs) { $gitlabPs } else { "not running" })) "evn/gitlab/start.ps1"

# Runner container
$runnerPs = docker ps --filter "name=^gitlab-runner$" --format "{{.Status}}" 2>$null
Add-Check "runner_container" ([bool]$runnerPs) ($(if ($runnerPs) { $runnerPs } else { "not running" })) "evn/gitlab/start_runner.ps1"

# config.toml
$cfgOk = Test-Path $RunnerConfig
Add-Check "runner_config" $cfgOk $RunnerConfig "register runner; see evn/gitlab/README.md"

if ($cfgOk) {
    $cfg = Get-Content $RunnerConfig -Raw
    Add-Check "runner_executor_docker" ($cfg -match 'executor\s*=\s*"docker"') "executor=docker in config.toml"
    Add-Check "runner_network" ($cfg -match 'network_mode\s*=\s*"gitlab_default"') "network_mode=gitlab_default"
    Add-Check "runner_gitlab_url" ($cfg -match 'http://gitlab:8000') "url=http://gitlab:8000 (container DNS)"
}

# Runner image local
docker image inspect gitlab/gitlab-runner:latest 2>$null | Out-Null
Add-Check "runner_image" ($LASTEXITCODE -eq 0) "gitlab/gitlab-runner:latest present" "evn/gitlab/start_runner.ps1"

# AICR on host
try {
    $hr = Invoke-WebRequest -Uri "$AicrUrl/health" -UseBasicParsing -TimeoutSec 5
    Add-Check "aicr_host" ($hr.StatusCode -eq 200) "$AicrUrl/health ok"
} catch {
    Add-Check "aicr_host" $false "AICR not reachable at $AicrUrl" "cd aicr-reviewer; .\scripts\run_local.ps1"
}

# AICR from job network (host.docker.internal)
$probe = docker run --rm --network gitlab_default docker.1ms.run/library/alpine:3.20 `
    sh -c "wget -qO- --timeout=5 http://host.docker.internal:8001/health 2>/dev/null || echo FAIL" 2>$null
$probeOk = $probe -and ($probe -notmatch "FAIL") -and ($probe -match "ok")
Add-Check "aicr_from_runner_network" $probeOk $(if ($probeOk) { "host.docker.internal:8001 ok from gitlab_default" } else { "cannot reach AICR from job network (probe: $probe)" }) `
    "Start AICR on host :8001; ensure extra_hosts in config.toml"

$failed = @($checks | Where-Object { -not $_.ok })
$report = @{
    ok      = ($failed.Count -eq 0)
    checks  = $checks
    failed  = $failed.Count
    gitlab  = $GitLabUrl
    aicr    = $AicrUrl
}

if ($Json) {
    $report | ConvertTo-Json -Depth 5
} else {
    Write-Host "=== L3b Runner preflight ===" -ForegroundColor Cyan
    foreach ($c in $checks) {
        $mark = if ($c.ok) { "[OK]" } else { "[!!]" }
        $color = if ($c.ok) { "Green" } else { "Yellow" }
        Write-Host "$mark $($c.id): $($c.detail)" -ForegroundColor $color
        if (-not $c.ok -and $c.fix) { Write-Host "     -> $($c.fix)" -ForegroundColor DarkGray }
    }
    Write-Host ""
    if ($report.ok) {
        Write-Host "All checks passed. Ready for L3b (push MR to trigger pipeline)." -ForegroundColor Green
    } else {
        Write-Host "$($failed.Count) check(s) need attention before L3b." -ForegroundColor Yellow
    }
}

if (-not $report.ok) { exit 1 }
exit 0

# L3b 跑前校验：GitLab + Runner 容器 + 网络可达 AICR
param(
    [string]$GitLabUrl = "http://localhost:8000",
    [string]$AicrUrl = "http://localhost:8001",
    [string]$GatewayUrl = "http://localhost:8010",
    [string]$ProjectPath = "java_group/datacalc-web",
    [switch]$OcrGatewayOnly,
    [switch]$Json
)

$ErrorActionPreference = "Continue"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$GitLabDir = Join-Path $RepoRoot "evn\gitlab"
$RunnerConfig = Join-Path $RepoRoot "evn\gitlab-runner\config\config.toml"

function Get-GitLabToken {
    param([switch]$PreferAdmin)
    $order = if ($PreferAdmin) { @("ROOT_PAT", "AICR_BOT_TOKEN") } else { @("AICR_BOT_TOKEN", "ROOT_PAT") }
    foreach ($name in $order) {
        $v = [Environment]::GetEnvironmentVariable($name, "Process")
        if ($v) { return $v }
    }
    $envFile = Join-Path $RepoRoot "evn\.env"
    if (Test-Path $envFile) {
        $found = @{}
        foreach ($line in Get-Content $envFile) {
            if ($line -match '^\s*(ROOT_PAT|AICR_BOT_TOKEN)\s*=\s*(.+)\s*$') {
                $val = $matches[2].Trim()
                if ($val -and $val -notmatch '^\.\.\.') { $found[$matches[1]] = $val }
            }
        }
        foreach ($name in $order) {
            if ($found[$name]) { return $found[$name] }
        }
    }
    return $null
}

function Add-OcrSecretMatches {
    param($Items, [string]$Scope, $FoundList)
    foreach ($v in @($Items)) {
        if ($null -ne $v -and $v.key -eq "OCR_GATEWAY_SECRET") {
            $FoundList.Add([pscustomobject]@{ scope = $Scope; protected = [bool]$v.protected })
        }
    }
}

function Test-OcrGatewaySecretVariable {
    param([string]$Token, [string]$BaseUrl, [string]$ProjectPath)
    if (-not $Token) { return $null }
    $encoded = [uri]::EscapeDataString($ProjectPath)
    $headers = @{ "PRIVATE-TOKEN" = $Token }
    try {
        $proj = Invoke-RestMethod -Uri "$BaseUrl/api/v4/projects/$encoded" -Headers $headers -TimeoutSec 10
        $found = [System.Collections.Generic.List[object]]::new()
        Add-OcrSecretMatches (Invoke-RestMethod -Uri "$BaseUrl/api/v4/projects/$($proj.id)/variables" -Headers $headers -TimeoutSec 10) "project" $found
        if ($proj.namespace.id) {
            Add-OcrSecretMatches (Invoke-RestMethod -Uri "$BaseUrl/api/v4/groups/$($proj.namespace.id)/variables" -Headers $headers -TimeoutSec 10) "group" $found
        }
        try {
            Add-OcrSecretMatches (Invoke-RestMethod -Uri "$BaseUrl/api/v4/admin/ci/variables" -Headers $headers -TimeoutSec 10) "instance" $found
        } catch { }
        if ($found.Count -eq 0) { return @{ ok = $false; detail = "OCR_GATEWAY_SECRET not found at project/group/instance" } }
        $allProtected = ($found | Where-Object { $_.protected }).Count -eq $found.Count
        $scopes = ($found | ForEach-Object { $_.scope }) -join ", "
        if ($allProtected) {
            return @{
                ok     = $false
                detail = "OCR_GATEWAY_SECRET only as Protected at: $scopes (MR from unprotected branch will not receive it → curl exit 22)"
            }
        }
        return @{ ok = $true; detail = "OCR_GATEWAY_SECRET at: $scopes (at least one unprotected)" }
    } catch {
        return $null
    }
}

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
    $badExtraHosts = $cfg -match 'extra_hosts\s*=\s*\[.*host-gateway'
    Add-Check "runner_extra_hosts" (-not $badExtraHosts) $(if ($badExtraHosts) { "extra_hosts host-gateway breaks Rancher Desktop (curl exit 7)" } else { "no host-gateway extra_hosts (ok for Rancher)" }) `
        "Remove extra_hosts host-gateway from config.toml; restart gitlab-runner"
}

function Invoke-JobNetworkProbe {
    param([string]$TargetUrl, [string]$RunnerCfg)
    $addHostArg = @()
    if ($RunnerCfg -match 'extra_hosts\s*=\s*\[.*host-gateway') {
        $addHostArg = @("--add-host", "host.docker.internal:host-gateway")
    }
    $probe = docker run --rm --network gitlab_default @addHostArg curlimages/curl:8.12.1 `
        curl -sf --connect-timeout 5 $TargetUrl 2>$null
    return ($LASTEXITCODE -eq 0) -and $probe
}

# Runner image local
docker image inspect gitlab/gitlab-runner:latest 2>$null | Out-Null
Add-Check "runner_image" ($LASTEXITCODE -eq 0) "gitlab/gitlab-runner:latest present" "evn/gitlab/start_runner.ps1"

# AICR on host (skip for OCR Gateway-only E2E)
if (-not $OcrGatewayOnly) {
    try {
        $hr = Invoke-WebRequest -Uri "$AicrUrl/health" -UseBasicParsing -TimeoutSec 5
        Add-Check "aicr_host" ($hr.StatusCode -eq 200) "$AicrUrl/health ok"
    } catch {
        Add-Check "aicr_host" $false "AICR not reachable at $AicrUrl" "cd aicr-reviewer; .\scripts\run_local.ps1"
    }
}

# Gateway on host (OCR CI)
try {
    $gr = Invoke-WebRequest -Uri "$GatewayUrl/health" -UseBasicParsing -TimeoutSec 5
    Add-Check "gateway_host" ($gr.StatusCode -eq 200) "$GatewayUrl/health ok"
} catch {
    Add-Check "gateway_host" $false "OCR Gateway not reachable at $GatewayUrl" "cd ocr-ci2; .\deploy\local\run.ps1"
}

# GitLab CI variable OCR_GATEWAY_SECRET (curl exit 22 when missing/protected → Gateway 401)
$glToken = Get-GitLabToken -PreferAdmin
$secretCheck = Test-OcrGatewaySecretVariable -Token $glToken -BaseUrl $GitLabUrl -ProjectPath $ProjectPath
if ($null -eq $secretCheck) {
    Add-Check "ocr_gateway_secret_var" $false "cannot query CI variables for $ProjectPath (need ROOT_PAT in evn/.env)" `
        "Admin/Group/Project → CI/CD → Variables → OCR_GATEWAY_SECRET=local-dev-secret"
} elseif (-not $secretCheck.ok) {
    Add-Check "ocr_gateway_secret_var" $false $secretCheck.detail `
        "Uncheck Protected on shared OCR_GATEWAY_SECRET, or enable MR access to protected variables"
} else {
    Add-Check "ocr_gateway_secret_var" $true $secretCheck.detail
}

# curl CI image for job-network probes
docker image inspect curlimages/curl:8.12.1 2>$null | Out-Null
Add-Check "ci_curl_image" ($LASTEXITCODE -eq 0) "curlimages/curl:8.12.1 present" "docker pull docker.m.daocloud.io/curlimages/curl:8.12.1; docker tag ... curlimages/curl:8.12.1"

$runnerCfgText = if ($cfgOk) { (Get-Content $RunnerConfig -Raw) } else { "" }
$gatewayProbeOk = Invoke-JobNetworkProbe -TargetUrl "http://host.docker.internal:8010/health" -RunnerCfg $runnerCfgText
Add-Check "gateway_from_runner_network" $gatewayProbeOk $(if ($gatewayProbeOk) { "host.docker.internal:8010 ok from gitlab_default" } else { "cannot reach Gateway from job network" }) `
    "Remove extra_hosts host-gateway from config.toml; cd ocr-ci2; .\deploy\local\run.ps1"

# AICR from job network (host.docker.internal)
if (-not $OcrGatewayOnly) {
    $probeOk = Invoke-JobNetworkProbe -TargetUrl "http://host.docker.internal:8001/health" -RunnerCfg $runnerCfgText
    Add-Check "aicr_from_runner_network" $probeOk $(if ($probeOk) { "host.docker.internal:8001 ok from gitlab_default" } else { "cannot reach AICR from job network" }) `
        "Start AICR on host :8001; remove extra_hosts host-gateway from config.toml"
}

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

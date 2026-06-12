param(
    [ValidateSet("L1", "L2", "L3", "daily", "all")]
    [string]$Level = "daily",
    [string]$RecordDir = "",
    [string]$Scenario = "",
    [switch]$SkipGitlabCheck,
    [switch]$SkipAicrStart,
    [switch]$KeepAicrRunning
)

$script:StartedAicrPid = $null

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$AicrRoot = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $AicrRoot
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Import-AicrEnv {
    # OS 环境变量（User/Machine）优先，evn/.env 仅回填缺省
    $fileVars = @{}
    $envFile = Join-Path $RepoRoot "evn\.env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^\s*([^#=]+)=(.*)$') {
                $k = $matches[1].Trim()
                $v = $matches[2].Trim()
                if ($k -and -not $fileVars.ContainsKey($k)) { $fileVars[$k] = $v }
            }
        }
    }
    $priority = @(
        'LLM_API_KEY', 'LLM_MODEL', 'LLM_PROVIDER', 'LLM_API_BASE',
        'AICR_BOT_TOKEN', 'GITLAB_URL', 'REVIEW_API_SECRET',
        'REVIEW_API_ALLOW_INSECURE', 'GITLAB_START_COMMAND'
    )
    foreach ($name in $priority) {
        $osVal = $null
        foreach ($scope in @('Process', 'User', 'Machine')) {
            $v = [Environment]::GetEnvironmentVariable($name, $scope)
            if ($v) { $osVal = $v; break }
        }
        if ($osVal) {
            [Environment]::SetEnvironmentVariable($name, $osVal, 'Process')
        } elseif ($fileVars.ContainsKey($name) -and $fileVars[$name]) {
            [Environment]::SetEnvironmentVariable($name, $fileVars[$name], 'Process')
        }
    }
    foreach ($pair in $fileVars.GetEnumerator()) {
        if ($priority -contains $pair.Key) { continue }
        if (-not [Environment]::GetEnvironmentVariable($pair.Key, 'Process') -and $pair.Value) {
            [Environment]::SetEnvironmentVariable($pair.Key, $pair.Value, 'Process')
        }
    }
}

function Write-JsonNoBom {
    param([string]$Path, [object]$Object)
    [System.IO.File]::WriteAllText($Path, ($Object | ConvertTo-Json), $Utf8NoBom)
}

function Stop-AicrListenerOnPort {
    param([int]$Port = 8001)
    $pattern = ":\s*$Port\s+.*LISTENING"
    netstat -ano | Select-String $pattern | ForEach-Object {
        if ($_ -match '\s+(\d+)\s*$') {
            $procId = [int]$matches[1]
            try {
                $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$procId" -ErrorAction Stop
                $cmd = $proc.CommandLine
                $name = $proc.Name
                if ($name -match '(?i)python' -and $cmd -match '(?i)uvicorn\s+main:app') {
                    Write-Host "Stopping AICR uvicorn (pid=$procId)..."
                    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                } else {
                    Write-Host "Skip pid $procId on port $Port ($name): not AICR uvicorn"
                }
            } catch {
                Write-Host "Skip pid $procId on port $Port: could not inspect process"
            }
        }
    }
    Start-Sleep -Seconds 2
}

function Test-ReviewApiSecretConfigured {
    $secret = [Environment]::GetEnvironmentVariable('REVIEW_API_SECRET', 'Process')
    if ($secret) { return $true }
    foreach ($scope in @('User', 'Machine')) {
        $v = [Environment]::GetEnvironmentVariable('REVIEW_API_SECRET', $scope)
        if ($v) { return $true }
    }
    return $false
}

function Test-AicrHealthDetail {
    param([string]$BaseUrl = "http://localhost:8001")
    try {
        $r = Invoke-WebRequest -Uri "$BaseUrl/health/detail" -UseBasicParsing -TimeoutSec 5
        return ($r.Content | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Test-AicrReviewReady {
    param($Detail)
    if (-not $Detail) { return $false }
    if ($Detail.review_auth_required) {
        return (Test-ReviewApiSecretConfigured)
    }
    return [bool]$Detail.review_api_allow_insecure
}

function Ensure-AicrRunning {
    param(
        [string]$RecordDir,
        [hashtable]$Meta,
        [switch]$RequireLlm
    )
    Import-AicrEnv
    $healthUrl = "http://localhost:8001"
    $detail = Test-AicrHealthDetail -BaseUrl $healthUrl
    $needStart = $false
    $needRestart = $false

    if (-not $detail) {
        $needStart = $true
    } elseif ($RequireLlm -and -not $detail.llm_key_set) {
        $needRestart = $true
    } elseif ($RequireLlm -and -not (Test-AicrReviewReady $detail)) {
        $needRestart = $true
    }

    if ($needRestart -and -not $SkipAicrStart) {
        if (-not $detail.llm_key_set) {
            Write-Host "AICR running but LLM_API_KEY not loaded; restarting with merged env..."
        } else {
            Write-Host "AICR blocks /review (need REVIEW_API_ALLOW_INSECURE=1 or REVIEW_API_SECRET); restarting..."
        }
        Stop-AicrListenerOnPort -Port 8001
        $detail = $null
        $needStart = $true
    }

    if ($needStart) {
        if ($SkipAicrStart) {
            Write-Warning "AICR not ready and -SkipAicrStart set; start AICR manually (run_local.ps1)."
            return $false
        }
        Write-Host "Starting AICR (uvicorn) in background..."
        $proc = Start-Process -FilePath $venvPy -ArgumentList @(
            "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"
        ) -WorkingDirectory $AicrRoot -PassThru -WindowStyle Hidden
        Start-Sleep -Seconds 6
        $script:StartedAicrPid = $proc.Id
        $Meta.aicr_pid = $proc.Id
        $Meta.aicr_started_by_acceptance = $true
        Write-JsonNoBom -Path (Join-Path $RecordDir "meta.json") -Object $Meta
        $detail = Test-AicrHealthDetail -BaseUrl $healthUrl
    }

    if ($RequireLlm -and -not $detail) {
        Write-Warning "AICR not reachable at $healthUrl (required for L3)."
        return $false
    }
    if ($detail) {
        Write-Host "AICR at $healthUrl (llm_key_set=$($detail.llm_key_set), token_set=$($detail.token_set), review_api_allow_insecure=$($detail.review_api_allow_insecure))"
    }
    if ($RequireLlm -and $detail -and -not $detail.llm_key_set) {
        Write-Warning "LLM_API_KEY still not visible to AICR. Set it in evn/.env or User/Machine env and restart AICR."
        return $false
    }
    if ($RequireLlm -and $detail -and -not (Test-AicrReviewReady $detail)) {
        if ($detail.review_auth_required) {
            Write-Warning "L3 /review requires REVIEW_API_SECRET in env (server has secret configured)."
        } else {
            Write-Warning "L3 /review blocked: set REVIEW_API_ALLOW_INSECURE=1 in evn/.env or configure REVIEW_API_SECRET."
        }
        return $false
    }
    return $true
}
if (-not $RecordDir) {
    $ts = Get-Date -Format "yyyy-MM-ddTHHmmss"
    $RecordDir = Join-Path $RepoRoot "test-results\$ts"
}
New-Item -ItemType Directory -Path $RecordDir -Force | Out-Null

$started = (Get-Date).ToUniversalTime().ToString('o')
$meta = @{
    run_id   = (Split-Path $RecordDir -Leaf)
    level    = $Level
    repo     = $RepoRoot
    hostname = $env:COMPUTERNAME
    user     = $env:USERNAME
    mode     = "direct-local-no-docker"
    started  = $started
}
Write-JsonNoBom -Path (Join-Path $RecordDir "meta.json") -Object $meta
Write-Host "Acceptance run: $RecordDir (level=$Level)"

$venvPy = Join-Path $AicrRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    python -m venv (Join-Path $AicrRoot ".venv")
    & $venvPy -m pip install -q -r (Join-Path $AicrRoot "requirements.txt")
}

function Should-Run($name) {
    switch ($Level) {
        "daily" { return $name -eq "L1" -or $name -eq "L2" }
        "all"   { return $true }
        default { return $Level -eq $name }
    }
}

$failed = $false
$l3Skipped = $false

try {
if (Should-Run "L1") {
    Write-Host "=== L1 smoke ==="
    $report = Join-Path $RecordDir "l1-smoke.json"
    & $venvPy (Join-Path $ScriptDir "smoke_test.py") --report-json $report
    if ($LASTEXITCODE -ne 0) { $failed = $true }
}

if (-not $failed -and (Should-Run "L2")) {
    Write-Host "=== L2 health ==="
    $null = Ensure-AicrRunning -RecordDir $RecordDir -Meta $meta
    $report = Join-Path $RecordDir "l2-health.json"
    & $venvPy (Join-Path $ScriptDir "health_check.py") --report-json $report
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "L2 failed: ensure evn/.env and AICR are running"
        $failed = $true
    }
}

if (-not $failed -and (Should-Run "L3")) {
    Write-Host "=== L3 E2E (GitLab via ensure_gitlab + LLM) ==="
    $l3Dir = Join-Path $RecordDir "l3"
    New-Item -ItemType Directory -Path $l3Dir -Force | Out-Null

    if (-not (Ensure-AicrRunning -RecordDir $RecordDir -Meta $meta -RequireLlm)) {
        $failed = $true
    }

    if (-not $failed -and -not $SkipGitlabCheck) {
        & (Join-Path $RepoRoot "test_data\scripts\ensure_gitlab.ps1")
        if ($LASTEXITCODE -ne 0) {
            $l3Skipped = $true
            if ($Level -eq "L3") { $failed = $true }
            else { Write-Warning "L3 skipped: GitLab not ready" }
        }
    }

    if (-not $l3Skipped -and -not $failed) {
        & (Join-Path $RepoRoot "test_data\scripts\bootstrap_demo.ps1")
        $scenario = if ($Scenario) { $Scenario } else { "S02_npe_optional" }
        $applyReport = Join-Path $l3Dir "apply.json"
        & $venvPy (Join-Path $RepoRoot "test_data\scripts\apply_scenario.py") `
            --scenario $scenario --report-json $applyReport
        if ($LASTEXITCODE -ne 0) { $failed = $true }

        if (-not $failed) {
            $apply = Get-Content $applyReport -Raw | ConvertFrom-Json
            $branch = $apply.scenarios[0].branch
            $scenarioId = $apply.scenarios[0].scenario_id
            $mrReport = Join-Path $l3Dir "mr.json"
            & $venvPy (Join-Path $RepoRoot "test_data\scripts\create_or_update_mr.py") `
                --source-branch $branch --target-branch main `
                --title "AICR acceptance $scenarioId" --report-json $mrReport
            if ($LASTEXITCODE -ne 0) { $failed = $true }

            if (-not $failed) {
                $mr = Get-Content $mrReport -Raw | ConvertFrom-Json
                $matrixDir = Join-Path $l3Dir $scenarioId
                & $venvPy (Join-Path $ScriptDir "prompt_matrix_test.py") `
                    --project-id $mr.project_id --mr-iid $mr.mr_iid `
                    --scenario-id $scenarioId --output-dir $matrixDir --force-full
                if ($LASTEXITCODE -ne 0) {
                    Write-Host "L3 matrix failed: one or more templates did not complete review." -ForegroundColor Yellow
                    $failed = $true
                }
            }
        }
    }
}

$reportZhArgs = @(
    (Join-Path $ScriptDir "report_zh.py"),
    "--record-dir", $RecordDir,
    "--level", $Level
)
if ($failed) { $reportZhArgs += "--failed" }
& $venvPy @reportZhArgs | Out-Null

$finished = (Get-Date).ToUniversalTime().ToString('o')
$summary = @{
    level      = $Level
    record_dir = $RecordDir
    failed     = $failed
    l3_skipped = $l3Skipped
    finished   = $finished
}
Write-JsonNoBom -Path (Join-Path $RecordDir "summary.json") -Object $summary

} finally {
    if ($script:StartedAicrPid -and -not $KeepAicrRunning) {
        Write-Host "Stopping acceptance-started AICR (pid=$($script:StartedAicrPid))..."
        Stop-Process -Id $script:StartedAicrPid -Force -ErrorAction SilentlyContinue
        $script:StartedAicrPid = $null
    }
}

if ($failed) { exit 1 }
Write-Host "Done: $RecordDir"
Write-Host "Chinese reports: l1-smoke.md, l2-health.md, l3.md, summary.zh.md"
Write-Host "View latest: .\.venv\Scripts\python.exe scripts\show_latest_report.py"
exit 0

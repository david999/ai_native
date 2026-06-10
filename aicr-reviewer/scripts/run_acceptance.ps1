param(
    [ValidateSet("L1", "L2", "L3", "daily", "all")]
    [string]$Level = "daily",
    [string]$RecordDir = "",
    [string]$Scenario = "",
    [switch]$SkipGitlabCheck,
    [switch]$SkipAicrStart
)

$ErrorActionPreference = "Stop"
$ScriptDir = $PSScriptRoot
$AicrRoot = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $AicrRoot
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Import-AicrEnv {
    $envFile = Join-Path $RepoRoot "evn\.env"
    if (Test-Path $envFile) {
        Get-Content $envFile | ForEach-Object {
            if ($_ -match '^\s*([^#=]+)=(.*)$') {
                $k = $matches[1].Trim()
                $v = $matches[2].Trim()
                if (-not [Environment]::GetEnvironmentVariable($k, 'Process') -and $v) {
                    [Environment]::SetEnvironmentVariable($k, $v, 'Process')
                }
            }
        }
    }
    foreach ($scope in @('User', 'Machine')) {
        foreach ($name in @(
            'LLM_API_KEY', 'LLM_MODEL', 'LLM_PROVIDER', 'AICR_BOT_TOKEN',
            'GITLAB_URL', 'REVIEW_API_SECRET', 'REVIEW_API_ALLOW_INSECURE'
        )) {
            $val = [Environment]::GetEnvironmentVariable($name, $scope)
            if ($val) {
                [Environment]::SetEnvironmentVariable($name, $val, 'Process')
            }
        }
    }
}

function Write-JsonNoBom {
    param([string]$Path, [object]$Object)
    [System.IO.File]::WriteAllText($Path, ($Object | ConvertTo-Json), $Utf8NoBom)
}

function Stop-ListenerOnPort {
    param([int]$Port)
    $pattern = ":\s*$Port\s+.*LISTENING"
    netstat -ano | Select-String $pattern | ForEach-Object {
        if ($_ -match '\s+(\d+)\s*$') {
            Stop-Process -Id ([int]$matches[1]) -Force -ErrorAction SilentlyContinue
        }
    }
    Start-Sleep -Seconds 2
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
    if (-not $detail) {
        $needStart = $true
    } elseif ($RequireLlm -and -not $detail.llm_key_set) {
        Write-Host "AICR running but LLM_API_KEY not loaded; restarting with merged env..."
        Stop-ListenerOnPort -Port 8001
        $needStart = $true
    }
    if ($needStart -and -not $SkipAicrStart) {
        Write-Host "Starting AICR (uvicorn) in background..."
        $proc = Start-Process -FilePath $venvPy -ArgumentList @(
            "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"
        ) -WorkingDirectory $AicrRoot -PassThru -WindowStyle Hidden
        Start-Sleep -Seconds 6
        $Meta.aicr_pid = $proc.Id
        Write-JsonNoBom -Path (Join-Path $RecordDir "meta.json") -Object $Meta
        $detail = Test-AicrHealthDetail -BaseUrl $healthUrl
    }
    if ($detail) {
        Write-Host "AICR at $healthUrl (llm_key_set=$($detail.llm_key_set), token_set=$($detail.token_set))"
    }
    if ($RequireLlm -and $detail -and -not $detail.llm_key_set) {
        Write-Warning "LLM_API_KEY still not visible to AICR. Set it in evn/.env or User/Machine env and restart AICR."
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
                if ($LASTEXITCODE -ne 0) { $failed = $true }
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

if ($failed) { exit 1 }
Write-Host "Done: $RecordDir"
Write-Host "Chinese reports: l1-smoke.md, l2-health.md, summary.zh.md"
Write-Host "View latest: .\.venv\Scripts\python.exe scripts\show_latest_report.py"
exit 0

param(
    [ValidateSet("L1", "L2", "L3", "L3-standard", "L3-full", "daily", "all")]
    [string]$Level = "daily",
    [string]$RecordDir = "",
    [string]$Scenario = "",
    [switch]$SkipGitlabCheck,
    [switch]$SkipAicrStart,
    [switch]$KeepAicrRunning
)

$script:StartedAicrPid = $null

$ErrorActionPreference = "Continue"
$ScriptDir = $PSScriptRoot
$AicrRoot = Split-Path -Parent $ScriptDir
$RepoRoot = Split-Path -Parent $AicrRoot
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
. (Join-Path $PSScriptRoot "acceptance_helpers.ps1")

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
        'REVIEW_API_ALLOW_INSECURE', 'GITLAB_START_COMMAND', 'REVIEW_DRY_RUN',
        'GITLAB_WEBHOOK_SECRET', 'GITLAB_WEBHOOK_ALLOW_INSECURE'
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
    [System.IO.File]::WriteAllText($Path, ($Object | ConvertTo-Json -Depth 10), $Utf8NoBom)
}

$script:AcceptanceTimingPhases = @()
$script:AcceptanceTimingStart = $null
$script:AcceptanceTimingCurrent = $null
$script:AcceptanceTimingSw = $null
$script:AcceptanceProgressLevel = $null

function Format-AcceptanceDuration {
    param([int]$Seconds)
    if ($Seconds -lt 60) { return "${Seconds}s" }
    $m = [math]::Floor($Seconds / 60)
    $s = $Seconds % 60
    if ($m -lt 60) { return "${m}m$("{0:D2}" -f $s)s" }
    $h = [math]::Floor($m / 60)
    $m = $m % 60
    return "${h}h$("{0:D2}" -f $m)m"
}

function Get-AcceptanceProgressPlan {
    param([string]$Level)
    $scenarios = @(
        @("scenario_S01_clean_refactor", "场景 S01 baseline"),
        @("scenario_S02_npe_optional", "场景 S02 baseline"),
        @("scenario_S03_empty_catch", "场景 S03 baseline"),
        @("scenario_S04_hardcoded_secret", "场景 S04 baseline"),
        @("scenario_S05_feign_no_timeout", "场景 S05 baseline")
    )
    $l3Tail = @(
        @("s02_matrix", "S02 三模板矩阵"),
        @("ci_gate", "CI 门禁"),
        @("gitlab_publish", "GitLab 发帖（S02）"),
        @("s06_incremental", "S06 增量评审"),
        @("phase_c", "Phase C 抽检")
    )
    switch ($Level) {
        "L3-full" {
            $plan = @(
                @("L1", "L1 冒烟"),
                @("L2", "L2 健康"),
                @("l3_env_setup", "L3 环境（GitLab + Demo）")
            )
            $plan += $scenarios
            $plan += $l3Tail
            return $plan
        }
        "L3-standard" {
            $plan = @(
                @("L1", "L1 冒烟"),
                @("L2", "L2 健康"),
                @("l3_env_setup", "L3 环境（GitLab + Demo）")
            )
            $plan += $scenarios
            return $plan
        }
        "daily" { return @(@("L1", "L1 冒烟"), @("L2", "L2 健康")) }
        "all"   { return @(@("L1", "L1 冒烟"), @("L2", "L2 健康")) }
        "L1"    { return @(@("L1", "L1 冒烟")) }
        "L2"    { return @(@("L2", "L2 健康")) }
        "L3"    { return @(@("L3", "L3 单场景 E2E")) }
        default { return @() }
    }
}

function Get-AcceptanceTotalElapsedSeconds {
    if (-not $script:AcceptanceTimingStart) { return 0 }
    return [int](((Get-Date).ToUniversalTime() - $script:AcceptanceTimingStart).TotalSeconds)
}

function Get-AcceptanceProgressStepIndex {
    param([string]$PhaseId)
    if (-not $script:AcceptanceProgressPlan) { return 0 }
    for ($i = 0; $i -lt $script:AcceptanceProgressPlan.Count; $i++) {
        if ($script:AcceptanceProgressPlan[$i][0] -eq $PhaseId) { return ($i + 1) }
    }
    return 0
}

function Initialize-AcceptanceProgress {
    param([string]$Level)
    $script:AcceptanceProgressLevel = $Level
    $script:AcceptanceProgressPlan = Get-AcceptanceProgressPlan -Level $Level
    if ($script:AcceptanceProgressPlan.Count -le 1) { return }
    Write-Host ""
    Write-Host "=== $Level 验收计划：共 $($script:AcceptanceProgressPlan.Count) 步 ===" -ForegroundColor Cyan
    for ($i = 0; $i -lt $script:AcceptanceProgressPlan.Count; $i++) {
        Write-Host ("  {0,2}. {1}" -f ($i + 1), $script:AcceptanceProgressPlan[$i][1])
    }
    Write-Host ""
}

function Write-AcceptanceProgressStart {
    param([string]$Id, [string]$Label)
    $step = Get-AcceptanceProgressStepIndex -PhaseId $Id
    $total = $script:AcceptanceProgressPlan.Count
    $elapsed = Format-AcceptanceDuration (Get-AcceptanceTotalElapsedSeconds)
    if ($step -eq 0) {
        Write-Host ">>> $Label | 总用时 $elapsed" -ForegroundColor Yellow
        return
    }
    $remaining = [Math]::Max(0, $total - $step)
    Write-Host "[$($script:AcceptanceProgressLevel) $step/$total] >>> $Label | 总用时 $elapsed | 剩余 $remaining 步" -ForegroundColor Green
}

function Write-AcceptanceProgressEnd {
    param(
        [string]$Id,
        [string]$Label,
        [int]$Seconds,
        [bool]$Ok = $true,
        [switch]$Skipped
    )
    $step = Get-AcceptanceProgressStepIndex -PhaseId $Id
    $total = $script:AcceptanceProgressPlan.Count
    $elapsed = Format-AcceptanceDuration (Get-AcceptanceTotalElapsedSeconds)
    $dur = Format-AcceptanceDuration $Seconds
    $status = if ($Skipped) { "未执行" } elseif ($Ok) { "通过" } else { "失败" }
    if ($step -eq 0) {
        Write-Host "<<< $Label $status $dur | 总用时 $elapsed" -ForegroundColor $(if ($Ok) { "Gray" } else { "Red" })
        return
    }
    $remaining = [Math]::Max(0, $total - $step)
    $color = if ($Skipped) { "DarkYellow" } elseif ($Ok) { "Gray" } else { "Red" }
    Write-Host "[$($script:AcceptanceProgressLevel) $step/$total] <<< $Label $status $dur | 总用时 $elapsed | 剩余 $remaining 步" -ForegroundColor $color
}

function Write-AcceptanceProgressSkipBatch {
    param([string]$Reason)
    foreach ($pair in @(
            @("s02_matrix", "S02 三模板矩阵"),
            @("ci_gate", "CI 门禁"),
            @("gitlab_publish", "GitLab 发帖（S02）"),
            @("s06_incremental", "S06 增量评审"),
            @("phase_c", "Phase C 抽检")
        )) {
        Write-AcceptanceProgressEnd -Id $pair[0] -Label $pair[1] -Seconds 0 -Ok $false -Skipped
        Write-Host "    （跳过原因：$Reason）" -ForegroundColor DarkYellow
    }
}

function Initialize-AcceptanceTiming {
    $script:AcceptanceTimingPhases = @()
    $script:AcceptanceTimingStart = (Get-Date).ToUniversalTime()
    $script:AcceptanceTimingCurrent = $null
    $script:AcceptanceTimingSw = $null
}

function Start-AcceptanceTimingPhase {
    param([string]$Id, [string]$Label)
    if ($script:AcceptanceTimingCurrent) {
        Write-Warning "Timing phase still open: $($script:AcceptanceTimingCurrent.id); closing as ok"
        Stop-AcceptanceTimingPhase -Ok $true | Out-Null
    }
    $script:AcceptanceTimingCurrent = @{ id = $Id; label = $Label }
    $script:AcceptanceTimingSw = [System.Diagnostics.Stopwatch]::StartNew()
    $script:AcceptanceTimingCurrent.started = (Get-Date).ToUniversalTime().ToString('o')
    Write-AcceptanceProgressStart -Id $Id -Label $Label
}

function Add-TimingPhaseEntry {
    param(
        [string]$Id,
        [string]$Label,
        [bool]$Ok,
        [int]$Seconds,
        [string]$Started = "",
        [switch]$Skipped,
        [string]$Reason = ""
    )
    $entry = @{
        id      = $Id
        label   = $Label
        seconds = $Seconds
        ok      = $Ok
    }
    if ($Started) { $entry.started = $Started }
    $entry.ended = (Get-Date).ToUniversalTime().ToString('o')
    if ($Skipped) {
        $entry.skipped = $true
        if ($Reason) { $entry.reason = $Reason }
        $entry.ok = $false
    }
    $script:AcceptanceTimingPhases += $entry
}

function Stop-AcceptanceTimingPhase {
    param(
        [bool]$Ok = $true,
        [switch]$Skipped,
        [string]$Reason = ""
    )
    if (-not $script:AcceptanceTimingCurrent) { return $null }
    if ($script:AcceptanceTimingSw) { $script:AcceptanceTimingSw.Stop() }
    $entry = @{
        id      = $script:AcceptanceTimingCurrent.id
        label   = $script:AcceptanceTimingCurrent.label
        started = $script:AcceptanceTimingCurrent.started
        ended   = (Get-Date).ToUniversalTime().ToString('o')
        seconds = [int]$script:AcceptanceTimingSw.Elapsed.TotalSeconds
        ok      = $Ok
    }
    if ($Skipped) {
        $entry.skipped = $true
        if ($Reason) { $entry.reason = $Reason }
    }
    $script:AcceptanceTimingPhases += $entry
    $script:AcceptanceTimingCurrent = $null
    $script:AcceptanceTimingSw = $null
    Write-AcceptanceProgressEnd -Id $entry.id -Label $entry.label -Seconds $entry.seconds -Ok $Ok -Skipped:$Skipped
    return $entry
}

function Add-SkippedTimingPhase {
    param([string]$Id, [string]$Label, [string]$Reason)
    $script:AcceptanceTimingPhases += @{
        id      = $Id
        label   = $Label
        skipped = $true
        reason  = $Reason
        seconds = $null
    }
}

function Add-L3FullSkippedExtras {
    param([string]$Reason = "scenario_suite failed")
    Write-AcceptanceProgressSkipBatch -Reason $Reason
    foreach ($pair in @(
            @("s02_matrix", "S02 三模板矩阵"),
            @("gitlab_publish", "GitLab 发帖（S02）"),
            @("ci_gate", "CI 门禁"),
            @("s06_incremental", "S06 增量评审"),
            @("phase_c", "Phase C 抽检")
        )) {
        Add-SkippedTimingPhase -Id $pair[0] -Label $pair[1] -Reason $Reason
    }
}

function Save-AcceptanceTimingJson {
    param([string]$RecordDir)
    Stop-AcceptanceTimingPhase -Ok $true | Out-Null
    $finished = (Get-Date).ToUniversalTime()
    $total = 0
    if ($script:AcceptanceTimingStart) {
        $total = [int](($finished - $script:AcceptanceTimingStart).TotalSeconds)
    }
    $obj = @{
        started       = $script:AcceptanceTimingStart.ToString('o')
        finished      = $finished.ToString('o')
        total_seconds = $total
        phases        = $script:AcceptanceTimingPhases
    }
    Write-JsonNoBom -Path (Join-Path $RecordDir "timing.json") -Object $obj
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
                Write-Host "Skip pid $procId on port ${Port}: could not inspect process"
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
    } elseif ($RequireLlm -and $detail.review_dry_run) {
        $dryEnv = [Environment]::GetEnvironmentVariable('REVIEW_DRY_RUN', 'Process')
        if ($dryEnv -ne '1') {
            Write-Host "AICR review_dry_run=true but env REVIEW_DRY_RUN=$dryEnv; restarting..."
            $needRestart = $true
        }
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

function Get-StandardScenarioIds {
    return @(
        "S01_clean_refactor",
        "S02_npe_optional",
        "S03_empty_catch",
        "S04_hardcoded_secret",
        "S05_feign_no_timeout"
    )
}

function Test-L3FullDryRunRequired {
    $dry = [Environment]::GetEnvironmentVariable('REVIEW_DRY_RUN', 'Process')
    if ($dry -eq '1') {
        Write-Error "L3-full requires REVIEW_DRY_RUN=0 in evn/.env (real GitLab publish)."
        return $false
    }
    return $true
}

function Initialize-L3Run {
    param(
        [string]$RecordDir,
        [hashtable]$Meta,
        [switch]$RequireLlm,
        [switch]$SkipGitlab,
        [ref]$L3Skipped
    )
    Import-AicrEnv
    $l3Dir = Join-Path $RecordDir "l3"
    New-Item -ItemType Directory -Path $l3Dir -Force | Out-Null

    if (-not (Ensure-AicrRunning -RecordDir $RecordDir -Meta $Meta -RequireLlm:$RequireLlm)) {
        return $null
    }
    if (-not $SkipGitlab) {
        if ((Invoke-AcceptanceProcess { & (Join-Path $RepoRoot "test_data\scripts\ensure_gitlab.ps1") }) -ne 0) {
            $L3Skipped.Value = $true
            return $null
        }
    }
    if ((Invoke-AcceptanceProcess { & (Join-Path $RepoRoot "test_data\scripts\bootstrap_demo.ps1") }) -ne 0) {
        return $null
    }
    return $l3Dir
}

function Show-ScenarioFailureDetail {
    param(
        [string]$ScenarioId,
        [string]$ScenDir
    )
    if (-not (Test-Path $ScenDir)) { return }
    Write-Host ""
    Write-Host "--- 场景失败详情 ($ScenarioId) ---" -ForegroundColor Yellow
    Invoke-AcceptancePython (Join-Path $ScriptDir "scenario_failure_report.py") `
        --scenario-dir $ScenDir --scenario-id $ScenarioId --write-md | Out-Null
    Write-Host "---" -ForegroundColor Yellow
}

function Invoke-L3ScenarioBaseline {
    param(
        [string]$ScenarioId,
        [string]$L3Dir,
        [hashtable]$ReleaseData,
        [switch]$AssertPublish,
        [string]$BranchOverride = ""
    )
    $scenDir = Join-Path $L3Dir $ScenarioId
    New-Item -ItemType Directory -Path $scenDir -Force | Out-Null
    $applyReport = Join-Path $scenDir "apply.json"
    $applyArgs = @(
        (Join-Path $RepoRoot "test_data\scripts\apply_scenario.py"),
        "--scenario", $ScenarioId,
        "--report-json", $applyReport
    )
    if ($BranchOverride) { $applyArgs += @("--branch", $BranchOverride) }
    if ((Invoke-AcceptancePython @applyArgs) -ne 0) {
        Show-ScenarioFailureDetail -ScenarioId $ScenarioId -ScenDir $scenDir
        return (New-AcceptanceResult @{ ok = $false; scenario_id = $ScenarioId })
    }

    $apply = Get-Content $applyReport -Raw | ConvertFrom-Json
    $branch = $apply.scenarios[0].branch
    $mrReport = Join-Path $scenDir "mr.json"
    if ((Invoke-AcceptancePython (Join-Path $RepoRoot "test_data\scripts\create_or_update_mr.py") `
            --source-branch $branch --target-branch main `
            --title "AICR acceptance $ScenarioId" --report-json $mrReport) -ne 0) {
        Show-ScenarioFailureDetail -ScenarioId $ScenarioId -ScenDir $scenDir
        return (New-AcceptanceResult @{ ok = $false; scenario_id = $ScenarioId })
    }

    $mr = Get-Content $mrReport -Raw | ConvertFrom-Json
    $reviewJson = Join-Path $scenDir "review.json"
    if ((Invoke-AcceptancePython (Join-Path $ScriptDir "review_single.py") `
            --project-id $mr.project_id --mr-iid $mr.mr_iid `
            --force-full --output $reviewJson --scenario-id $ScenarioId) -ne 0) {
        Show-ScenarioFailureDetail -ScenarioId $ScenarioId -ScenDir $scenDir
        return (New-AcceptanceResult @{ ok = $false; scenario_id = $ScenarioId })
    }

    $review = Get-Content $reviewJson -Raw | ConvertFrom-Json
    $validateReport = Join-Path $scenDir "validate.json"
    $valOk = ((Invoke-AcceptancePython (Join-Path $RepoRoot "test_data\scripts\validate_scenario.py") `
            --scenario-id $ScenarioId --review-json $reviewJson `
            --report-json $validateReport --tolerance 5) -eq 0)
    if (-not $valOk) {
        Write-Host "Validation failed for $ScenarioId; retrying review once..."
        if ((Invoke-AcceptancePython (Join-Path $ScriptDir "review_single.py") `
                --project-id $mr.project_id --mr-iid $mr.mr_iid `
                --force-full --output $reviewJson --scenario-id $ScenarioId) -eq 0) {
            $valOk = ((Invoke-AcceptancePython (Join-Path $RepoRoot "test_data\scripts\validate_scenario.py") `
                    --scenario-id $ScenarioId --review-json $reviewJson `
                    --report-json $validateReport --tolerance 5) -eq 0)
        }
    }

    $publishOk = $true
    if ($AssertPublish -and $ScenarioId -eq "S02_npe_optional") {
        $pubReport = Join-Path $scenDir "publish.json"
        $publishOk = ((Invoke-AcceptancePython (Join-Path $RepoRoot "test_data\scripts\assert_gitlab_publish.py") `
                --project-id $mr.project_id --mr-iid $mr.mr_iid `
                --expected-score $review.score --report-json $pubReport) -eq 0)
    }

    $gitlabUrl = [Environment]::GetEnvironmentVariable('GITLAB_URL', 'Process')
    if (-not $gitlabUrl) { $gitlabUrl = "http://localhost:8000" }
    $mrUrl = if ($mr.web_url) { $mr.web_url } else {
        "$($gitlabUrl.TrimEnd('/'))/demo/spring-cloud-demo/-/merge_requests/$($mr.mr_iid)"
    }

    $entry = @{
        scenario_id    = $ScenarioId
        score          = $review.score
        validation_ok  = $valOk
        publish_ok     = $publishOk
        mr_url         = $mrUrl
        project_id     = $mr.project_id
        mr_iid         = $mr.mr_iid
        branch         = $branch
        note           = if ($valOk) { "" } else { "validation failed after retry" }
    }
    if ($ReleaseData.scenarios -isnot [System.Collections.ArrayList]) {
        if ($ReleaseData.scenarios) {
            [void]($ReleaseData.scenarios = [System.Collections.ArrayList]@($ReleaseData.scenarios))
        } else {
            [void]($ReleaseData.scenarios = [System.Collections.ArrayList]@())
        }
    }
    [void]$ReleaseData.scenarios.Add($entry)

    $ok = $valOk -and $publishOk
    if (-not $ok) {
        Show-ScenarioFailureDetail -ScenarioId $ScenarioId -ScenDir $scenDir
    }
    if (-not $valOk) {
        if ($ReleaseData.warnings -isnot [System.Collections.ArrayList]) {
            [void]($ReleaseData.warnings = [System.Collections.ArrayList]@())
        }
        [void]$ReleaseData.warnings.Add("Scenario $ScenarioId validation flaky/failed")
    }
    return (New-AcceptanceResult @{ ok = $ok; entry = $entry; mr = $mr; review = $review })
}

function Invoke-L3StandardSuite {
    param(
        [string]$RecordDir,
        [hashtable]$Meta,
        [hashtable]$ReleaseData,
        [switch]$SkipGitlab,
        [switch]$AssertPublish
    )
    $l3Skipped = $false
    Start-AcceptanceTimingPhase -Id "l3_env_setup" -Label "L3 环境（GitLab + Demo）"
    $l3Dir = Initialize-L3Run -RecordDir $RecordDir -Meta $Meta -RequireLlm `
        -SkipGitlab:$SkipGitlab -L3Skipped ([ref]$l3Skipped)
    if ($l3Skipped) {
        Stop-AcceptanceTimingPhase -Ok $false -Skipped -Reason "GitLab not ready" | Out-Null
        if ($Level -in @("L3-standard", "L3-full")) {
            return (New-AcceptanceResult @{ ok = $false; skipped = $true })
        }
        Write-Warning "L3 skipped: GitLab not ready"
        return (New-AcceptanceResult @{ ok = $true; skipped = $true })
    }
    if (-not $l3Dir) {
        Stop-AcceptanceTimingPhase -Ok $false | Out-Null
        return (New-AcceptanceResult @{ ok = $false; skipped = $false })
    }
    Stop-AcceptanceTimingPhase -Ok $true | Out-Null

    $suiteOk = $true
    $suiteSw = [System.Diagnostics.Stopwatch]::StartNew()
    $suiteStarted = (Get-Date).ToUniversalTime().ToString('o')
    foreach ($sid in Get-StandardScenarioIds) {
        Write-Host "=== Scenario $sid (baseline) ==="
        Start-AcceptanceTimingPhase -Id "scenario_$sid" -Label "场景 $sid"
        $r = Invoke-L3ScenarioBaseline -ScenarioId $sid -L3Dir $l3Dir -ReleaseData $ReleaseData -AssertPublish:$AssertPublish
        $scenOk = Get-InvokeHashtableOk -Result $r
        Stop-AcceptanceTimingPhase -Ok $scenOk | Out-Null
        if (-not $scenOk) { $suiteOk = $false }
    }
    $suiteSw.Stop()
    Add-TimingPhaseEntry -Id "scenario_suite" -Label "场景套件 S01–S05" -Ok $suiteOk `
        -Seconds ([int]$suiteSw.Elapsed.TotalSeconds) -Started $suiteStarted
    $ReleaseData.phases = @{}
    $ReleaseData.phases["scenario_suite"] = @{ ok = $suiteOk }
    Write-JsonNoBom -Path (Join-Path $l3Dir "release_data.json") -Object $ReleaseData
    return (New-AcceptanceResult @{ ok = $suiteOk; l3Dir = $l3Dir; skipped = $false })
}

function Invoke-L3FullExtras {
    param(
        [string]$L3Dir,
        [hashtable]$ReleaseData,
        [object]$S02Mr,
        [object]$S02Review
    )
    $extrasOk = $true

    Write-Host "=== S02 prompt matrix ==="
    Start-AcceptanceTimingPhase -Id "s02_matrix" -Label "S02 三模板矩阵"
    $matrixDir = Join-Path $L3Dir "S02_npe_optional_matrix"
    $matrixOk = ((Invoke-AcceptancePython (Join-Path $ScriptDir "prompt_matrix_test.py") `
        --project-id $S02Mr.project_id --mr-iid $S02Mr.mr_iid `
        --scenario-id "S02_npe_optional" --output-dir $matrixDir --force-full) -eq 0)
    if (-not $matrixOk) { $extrasOk = $false }
    $matrixSummary = $null
    $msPath = Join-Path $matrixDir "matrix_summary.json"
    if (Test-Path $msPath) {
        $matrixSummary = Get-Content $msPath -Raw | ConvertFrom-Json
        $ReleaseData.matrix_summary = $matrixSummary
    }
    $ReleaseData.phases["s02_matrix"] = @{ ok = $matrixOk }
    Stop-AcceptanceTimingPhase -Ok $matrixOk | Out-Null

    Write-Host "=== CI review gate (S02 MR, expect block on low score, cached) ==="
    Start-AcceptanceTimingPhase -Id "ci_gate" -Label "CI 门禁"
    $env:AICR_PROJECT_ID = "$($S02Mr.project_id)"
    $env:AICR_MR_IID = "$($S02Mr.mr_iid)"
    $env:AICR_REVIEW_URL = "http://localhost:8001"
    $gateSecret = [Environment]::GetEnvironmentVariable('REVIEW_API_SECRET', 'Process')
    if (-not $gateSecret) {
        foreach ($scope in @('User', 'Machine')) {
            $gateSecret = [Environment]::GetEnvironmentVariable('REVIEW_API_SECRET', $scope)
            if ($gateSecret) { break }
        }
    }
    $gateArgs = @{
        CachedScore     = [double]$S02Review.score
        CachedCompleted = [bool]$S02Review.review_completed
    }
    if ($gateSecret) { $gateArgs['Secret'] = $gateSecret }
    $gateExit = Invoke-AcceptanceProcess { & (Join-Path $ScriptDir "ci_review_gate.ps1") @gateArgs }
    $gateOk = ($gateExit -eq 1)
    if (-not $gateOk) {
        Write-Warning "CI gate expected exit 1 (low score block) but got $gateExit"
        $extrasOk = $false
    }
    $ReleaseData.phases["ci_gate"] = @{ ok = $gateOk; exit_code = $gateExit; expected_exit = 1 }
    Stop-AcceptanceTimingPhase -Ok $gateOk | Out-Null

    Start-AcceptanceTimingPhase -Id "gitlab_publish" -Label "GitLab 发帖（S02）"
    $pubOk = [bool]$ReleaseData.phases["gitlab_publish"].ok
    if (-not $pubOk) { $extrasOk = $false }
    Stop-AcceptanceTimingPhase -Ok $pubOk | Out-Null

    Write-Host "=== S06 incremental ==="
    Start-AcceptanceTimingPhase -Id "s06_incremental" -Label "S06 增量评审"
    $s06Branch = "aicr-test/S06_incremental"
    $s06Dir = Join-Path $L3Dir "S06_incremental"
    New-Item -ItemType Directory -Path $s06Dir -Force | Out-Null
    if ((Invoke-AcceptancePython (Join-Path $RepoRoot "test_data\scripts\apply_scenario.py") `
            --scenario "S02_npe_optional" --branch $s06Branch `
            --report-json (Join-Path $s06Dir "apply1.json")) -ne 0) {
        $extrasOk = $false
        Stop-AcceptanceTimingPhase -Ok $false | Out-Null
        Add-SkippedTimingPhase -Id "phase_c" -Label "Phase C 抽检" -Reason "S06 incremental failed"
    }
    else {
        if ((Invoke-AcceptancePython (Join-Path $RepoRoot "test_data\scripts\create_or_update_mr.py") `
                --source-branch $s06Branch --target-branch main `
                --title "AICR acceptance S06_incremental" `
                --report-json (Join-Path $s06Dir "mr.json")) -ne 0) {
            $extrasOk = $false
            Stop-AcceptanceTimingPhase -Ok $false | Out-Null
            Add-SkippedTimingPhase -Id "phase_c" -Label "Phase C 抽检" -Reason "S06 MR failed"
        }
        else {
            $s06Mr = Get-Content (Join-Path $s06Dir "mr.json") -Raw | ConvertFrom-Json
            $r1 = Join-Path $s06Dir "review1.json"
            $firstOk = ((Invoke-AcceptancePython (Join-Path $ScriptDir "review_single.py") `
                    --project-id $s06Mr.project_id --mr-iid $s06Mr.mr_iid `
                    --force-full --output $r1 --scenario-id "S06_incremental") -eq 0)
            $firstReview = Get-Content $r1 -Raw | ConvertFrom-Json

            Invoke-AcceptancePython (Join-Path $RepoRoot "test_data\scripts\apply_scenario.py") `
                --scenario "S06_incremental" --branch $s06Branch --incremental `
                --report-json (Join-Path $s06Dir "apply2.json") | Out-Null
            $r2 = Join-Path $s06Dir "review2.json"
            $secondOk = ((Invoke-AcceptancePython (Join-Path $ScriptDir "review_single.py") `
                    --project-id $s06Mr.project_id --mr-iid $s06Mr.mr_iid `
                    --no-force-full --output $r2 --scenario-id "S06_incremental") -eq 0)
            $secondReview = Get-Content $r2 -Raw | ConvertFrom-Json

            $val2Ok = ((Invoke-AcceptancePython (Join-Path $RepoRoot "test_data\scripts\validate_scenario.py") `
                    --scenario-id "S06_incremental" --review-json $r2 `
                    --report-json (Join-Path $s06Dir "validate2.json") --tolerance 5) -eq 0)
            $s06Ok = $firstOk -and $secondOk -and $val2Ok
            if (-not $s06Ok) { $extrasOk = $false }
            $ReleaseData.incremental = @{
                first_score  = $firstReview.score
                first_sha    = $firstReview.prompt_sha256
                second_score = $secondReview.score
                second_sha   = $secondReview.prompt_sha256
                second_ok    = ($secondOk -and $val2Ok)
            }
            $ReleaseData.phases["s06_incremental"] = @{ ok = $s06Ok }
            Stop-AcceptanceTimingPhase -Ok $s06Ok | Out-Null

            Write-Host "=== Phase C smoke ==="
            Start-AcceptanceTimingPhase -Id "phase_c" -Label "Phase C 抽检"
            $phaseReport = Join-Path $s06Dir "phase_c.json"
            $phaseOk = ((Invoke-AcceptancePython (Join-Path $ScriptDir "phase_c_smoke.py") `
                    --project-id $s06Mr.project_id --mr-iid $s06Mr.mr_iid `
                    --report-json $phaseReport) -eq 0)
            if (-not $phaseOk) { $extrasOk = $false }
            $ReleaseData.phases["phase_c"] = @{ ok = $phaseOk }
            Stop-AcceptanceTimingPhase -Ok $phaseOk | Out-Null
        }
    }

    Write-JsonNoBom -Path (Join-Path $L3Dir "release_data.json") -Object $ReleaseData
    return $extrasOk
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

$script:AcceptanceLogPath = Join-Path $RecordDir "acceptance.log"
$script:AcceptanceTranscriptStarted = $false
try {
    Start-Transcript -Path $script:AcceptanceLogPath -Force | Out-Null
    $script:AcceptanceTranscriptStarted = $true
    Write-Host "Console log: $script:AcceptanceLogPath"
} catch {
    Write-Warning "Could not start transcript (acceptance.log): $_"
}

$script:AcceptanceVenvPy = Join-Path $AicrRoot ".venv\Scripts\python.exe"
$venvPy = $script:AcceptanceVenvPy
if (-not (Test-Path $venvPy)) {
    python -m venv (Join-Path $AicrRoot ".venv")
    Invoke-AcceptanceProcess { & $venvPy -m pip install -q -r (Join-Path $AicrRoot "requirements.txt") } -Silent | Out-Null
}

function Should-Run($name) {
    switch ($Level) {
        "daily" { return $name -eq "L1" -or $name -eq "L2" }
        "all"   { return $name -in @("L1", "L2", "L3") }
        "L3-full" { return $name -in @("L1", "L2", "L3-full") }
        default { return $Level -eq $name }
    }
}

$failed = $false
$l3Skipped = $false

try {
Initialize-AcceptanceTiming
Initialize-AcceptanceProgress -Level $Level

if ($Level -eq "L3-full") {
    Import-AicrEnv
    if (-not (Ensure-AicrRunning -RecordDir $RecordDir -Meta $meta -RequireLlm)) {
        Write-Host ""
        Write-Host "L3-full 已中止：AICR 无法启动或未就绪（含 LLM/鉴权/dry-run）。" -ForegroundColor Red
        if ($SkipAicrStart) {
            Write-Host "已指定 -SkipAicrStart：请先手动 cd aicr-reviewer; .\scripts\run_local.ps1" -ForegroundColor Yellow
        } else {
            Write-Host "可手动: cd aicr-reviewer; .\scripts\run_local.ps1" -ForegroundColor Yellow
        }
        exit 1
    }
    Write-Host ""
    $preflightReport = Join-Path $RecordDir "preflight.json"
    if ((Invoke-AcceptancePython (Join-Path $ScriptDir "l3_full_preflight.py") `
            --record-dir $RecordDir --report-json $preflightReport) -ne 0) {
        Write-Host ""
        Write-Host "L3-full 已中止：请按上方「需要您处理」逐项修复后重跑。" -ForegroundColor Red
        exit 1
    }
    if (Test-Path $preflightReport) {
        $pf = Get-Content $preflightReport -Raw | ConvertFrom-Json
        if ($pf.infra_ready) {
            $SkipGitlabCheck = $true
            Write-Host "Preflight: GitLab 已就绪，L3 阶段跳过重复 ensure_gitlab" -ForegroundColor DarkGray
        }
    }
    Write-Host ""
}

if (Should-Run "L1") {
    Write-Host "=== L1 smoke ==="
    Start-AcceptanceTimingPhase -Id "L1" -Label "L1 冒烟"
    $report = Join-Path $RecordDir "l1-smoke.json"
    $l1Ok = ((Invoke-AcceptancePython (Join-Path $ScriptDir "smoke_test.py") --report-json $report) -eq 0)
    if (-not $l1Ok) { $failed = $true }
    Stop-AcceptanceTimingPhase -Ok $l1Ok | Out-Null
}

if (-not $failed -and (Should-Run "L2")) {
    Write-Host "=== L2 health ==="
    Start-AcceptanceTimingPhase -Id "L2" -Label "L2 健康"
    $null = Ensure-AicrRunning -RecordDir $RecordDir -Meta $meta
    $report = Join-Path $RecordDir "l2-health.json"
    $l2Ok = ((Invoke-AcceptancePython (Join-Path $ScriptDir "health_check.py") --report-json $report) -eq 0)
    if (-not $l2Ok) {
        Write-Warning "L2 failed: ensure evn/.env and AICR are running"
        $failed = $true
    }
    Stop-AcceptanceTimingPhase -Ok $l2Ok | Out-Null
}

if (-not $failed -and (Should-Run "L3")) {
    Write-Host "=== L3 E2E (GitLab via ensure_gitlab + LLM) ==="
    $l3Dir = Join-Path $RecordDir "l3"
    New-Item -ItemType Directory -Path $l3Dir -Force | Out-Null

    if (-not (Ensure-AicrRunning -RecordDir $RecordDir -Meta $meta -RequireLlm)) {
        $failed = $true
    }

    if (-not $failed -and -not $SkipGitlabCheck) {
        if ((Invoke-AcceptanceProcess { & (Join-Path $RepoRoot "test_data\scripts\ensure_gitlab.ps1") }) -ne 0) {
            $l3Skipped = $true
            if ($Level -eq "L3") { $failed = $true }
            else { Write-Warning "L3 skipped: GitLab not ready" }
        }
    }

    if (-not $l3Skipped -and -not $failed) {
        Invoke-AcceptanceProcess { & (Join-Path $RepoRoot "test_data\scripts\bootstrap_demo.ps1") } | Out-Null
        $scenario = if ($Scenario) { $Scenario } else { "S02_npe_optional" }
        $applyReport = Join-Path $l3Dir "apply.json"
        if ((Invoke-AcceptancePython (Join-Path $RepoRoot "test_data\scripts\apply_scenario.py") `
                --scenario $scenario --report-json $applyReport) -ne 0) {
            $failed = $true
        }

        if (-not $failed) {
            $apply = Get-Content $applyReport -Raw | ConvertFrom-Json
            $branch = $apply.scenarios[0].branch
            $scenarioId = $apply.scenarios[0].scenario_id
            $mrReport = Join-Path $l3Dir "mr.json"
            if ((Invoke-AcceptancePython (Join-Path $RepoRoot "test_data\scripts\create_or_update_mr.py") `
                    --source-branch $branch --target-branch main `
                    --title "AICR acceptance $scenarioId" --report-json $mrReport) -ne 0) {
                $failed = $true
            }

            if (-not $failed) {
                $mr = Get-Content $mrReport -Raw | ConvertFrom-Json
                $matrixDir = Join-Path $l3Dir $scenarioId
                if ((Invoke-AcceptancePython (Join-Path $ScriptDir "prompt_matrix_test.py") `
                        --project-id $mr.project_id --mr-iid $mr.mr_iid `
                        --scenario-id $scenarioId --output-dir $matrixDir --force-full) -ne 0) {
                    Write-Host "L3 matrix failed: one or more templates did not complete review." -ForegroundColor Yellow
                    $failed = $true
                }
            }
        }
    }
}

if (-not $failed -and (Should-Run "L3-standard")) {
    Write-Host "=== L3-standard (S01-S05 baseline + validate) ==="
    $releaseData = @{
        scenarios = [System.Collections.ArrayList]@()
        warnings  = [System.Collections.ArrayList]@()
        phases    = @{}
    }
    $r = Invoke-L3StandardSuite -RecordDir $RecordDir -Meta $meta -ReleaseData $releaseData `
        -SkipGitlab:$SkipGitlabCheck -AssertPublish:$false
    $suite = Get-InvokeHashtableResult -Result $r
    if ($suite -and $suite.skipped) {
        $l3Skipped = $true
        if ($Level -eq "L3-standard") { $failed = $true }
    } elseif (-not (Get-InvokeHashtableOk -Result $r)) {
        $failed = $true
    }
}

if (-not $failed -and (Should-Run "L3-full")) {
    Write-Host "=== L3-full delivery acceptance ==="
    Import-AicrEnv
    if (-not (Test-L3FullDryRunRequired)) { $failed = $true }
    if (-not $failed) {
        $releaseData = @{
            scenarios = [System.Collections.ArrayList]@()
            warnings  = [System.Collections.ArrayList]@()
            phases    = @{}
        }
        $r = Invoke-L3StandardSuite -RecordDir $RecordDir -Meta $meta -ReleaseData $releaseData `
            -SkipGitlab:$SkipGitlabCheck -AssertPublish
        $suite = Get-InvokeHashtableResult -Result $r
        if ($suite -and $suite.skipped) {
            $l3Skipped = $true
            $failed = $true
            Add-L3FullSkippedExtras -Reason "GitLab not ready"
        } elseif (-not (Get-InvokeHashtableOk -Result $r)) {
            $failed = $true
            Add-L3FullSkippedExtras -Reason "scenario_suite failed"
        } else {
            $s02 = $releaseData.scenarios | Where-Object { $_.scenario_id -eq "S02_npe_optional" } | Select-Object -First 1
            if (-not $s02) {
                Write-Warning "S02 scenario missing from release data"
                $failed = $true
                Add-L3FullSkippedExtras -Reason "S02 missing"
            } else {
                $releaseData.phases["gitlab_publish"] = @{ ok = [bool]$s02.publish_ok }
                if (-not $s02.publish_ok) {
                    $failed = $true
                    Add-L3FullSkippedExtras -Reason "S02 GitLab publish failed"
                } else {
                $s02ReviewPath = Join-Path $suite.l3Dir "S02_npe_optional\review.json"
                $s02Review = Get-Content $s02ReviewPath -Raw | ConvertFrom-Json
                $s02Mr = @{ project_id = $s02.project_id; mr_iid = $s02.mr_iid }
                if (-not $failed -and -not (Invoke-L3FullExtras -L3Dir $suite.l3Dir -ReleaseData $releaseData -S02Mr $s02Mr -S02Review $s02Review)) {
                    $failed = $true
                }
                }
            }
        }
    }
}

Save-AcceptanceTimingJson -RecordDir $RecordDir

if ($Level -eq "L3-full") {
    $relArgs = @(
        (Join-Path $ScriptDir "write_release_report.py"),
        "--record-dir", $RecordDir,
        "--level", "L3-full"
    )
    if ($failed) { $relArgs += "--failed" }
    Invoke-AcceptancePython @relArgs | Out-Null
}

$reportZhArgs = @(
    (Join-Path $ScriptDir "report_zh.py"),
    "--record-dir", $RecordDir,
    "--level", $Level
)
if ($failed) { $reportZhArgs += "--failed" }
Invoke-AcceptancePython @reportZhArgs | Out-Null

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
    if ($script:AcceptanceTranscriptStarted) {
        try { Stop-Transcript | Out-Null } catch {}
        $script:AcceptanceTranscriptStarted = $false
    }
    if ($script:StartedAicrPid -and -not $KeepAicrRunning) {
        Write-Host "Stopping acceptance-started AICR (pid=$($script:StartedAicrPid))..."
        Stop-Process -Id $script:StartedAicrPid -Force -ErrorAction SilentlyContinue
        $script:StartedAicrPid = $null
    }
}

if ($failed) { exit 1 }
$totalElapsed = Format-AcceptanceDuration (Get-AcceptanceTotalElapsedSeconds)
$verdict = if ($failed) { "不通过" } else { "通过" }
Write-Host ""
Write-Host "=== 验收结束 === 结论: $verdict | 总用时 $totalElapsed | 报告: $RecordDir" -ForegroundColor $(if ($failed) { "Red" } else { "Green" })
Write-Host "Done: $RecordDir"
Write-Host "Console log: acceptance.log"
Write-Host "Chinese reports: l1-smoke.md, l2-health.md, l3.md, summary.zh.md"
if ($Level -eq "L3-full") { Write-Host "Delivery report: release.zh.md" }
Write-Host "View latest: .\.venv\Scripts\python.exe scripts\show_latest_report.py"
exit 0

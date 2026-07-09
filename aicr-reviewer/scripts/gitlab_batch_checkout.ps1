#requires -Version 5.1
# 编码：须保存为 UTF-8 BOM；无 BOM 时 Windows PowerShell 5.1 会把中文乱码导致语法错误。
<#
.SYNOPSIS
    批量将本地已 clone 的工程 checkout 到指定分支，并在远端存在时 pull 最新代码。

.DESCRIPTION
    与 gitlab_group_clone.ps1 使用相同的本地目录布局（默认 D:\agit\<group>\<project>）。
    执行顺序：
    1) 预检：所有目标仓库必须存在且工作区干净（无未提交变更）；
    2) 任一不通过则整批中断，不修改任何仓库；
    3) 全部通过后，再逐个 fetch / checkout / pull。

.PARAMETER TargetGroupPath
    GitLab Group 路径（与 clone 脚本一致），如 aulton-ms-finance。

.PARAMETER ProjectNames
    该 Group 下的项目名（path，非 id），可多个或逗号分隔。
    示例：-ProjectNames aulton-ms-pay,aulton-ms-split-bill

.PARAMETER ProjectListFile
    可选：每行一个项目名；# 开头为注释。与 -ProjectNames 合并去重。

.PARAMETER Branch
    目标分支名（默认 release）。

.PARAMETER DownloadRoot
    本地仓库根目录（默认 D:\agit）。

.EXAMPLE
  # 将 finance 组下两个工程切到 release 并 pull
  .\scripts\gitlab_batch_checkout.ps1 `
    -TargetGroupPath aulton-ms-finance `
    -ProjectNames aulton-ms-pay,aulton-ms-split-bill

.EXAMPLE
  # 从文件读取项目列表
  .\scripts\gitlab_batch_checkout.ps1 `
    -TargetGroupPath aulton-ms-finance `
    -ProjectListFile D:\agit\finance_projects.txt `
    -Branch release
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetGroupPath,
    [string[]]$ProjectNames = @(),
    [string]$ProjectListFile = "",
    [string]$Branch = "release",
    [string]$DownloadRoot = "D:\agit"
)

$ErrorActionPreference = "Stop"

if (-not $TargetGroupPath) { throw "TargetGroupPath 不能为空" }
if (-not $Branch) { throw "Branch 不能为空" }
if (-not $DownloadRoot) { throw "DownloadRoot 不能为空" }

$TargetGroupPath = $TargetGroupPath.Trim().Trim("/")
$ReportDir = Join-Path $DownloadRoot "_reports"
New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null

$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
function Write-JsonFile {
    param([string]$Path, [object]$Object)
    [System.IO.File]::WriteAllText($Path, ($Object | ConvertTo-Json -Depth 10), $Utf8NoBom)
}

# 解析项目名：支持数组、逗号分隔、列表文件
function Resolve-ProjectNames {
    param(
        [string[]]$Names,
        [string]$ListFile
    )
    $result = @()
    foreach ($raw in $Names) {
        if (-not $raw) { continue }
        foreach ($part in ($raw -split ",")) {
            $trimmed = $part.Trim()
            if ($trimmed) { $result += $trimmed }
        }
    }
    if ($ListFile) {
        if (-not (Test-Path $ListFile)) {
            throw "ProjectListFile 不存在: $ListFile"
        }
        Get-Content $ListFile -Encoding UTF8 | ForEach-Object {
            $line = $_.Trim()
            if (-not $line -or $line.StartsWith("#")) { return }
            $result += $line
        }
    }
    $unique = @()
    foreach ($n in $result) {
        if ($unique -notcontains $n) { $unique += $n }
    }
    return [string[]]@($unique)
}

# 与 gitlab_group_clone.ps1 相同的路径规则
function Get-SafeRepoDirectory {
    param(
        [string]$GroupPath,
        [string]$ProjectName
    )
    $parts = $GroupPath -split "/"
    $safeParts = $parts | ForEach-Object { $_ -replace '[\\/:*?"<>|]', '_' }
    $safeProjectName = $ProjectName -replace '[\\/:*?"<>|]', '_'
    return Join-Path $DownloadRoot (Join-Path ($safeParts -join "\") $safeProjectName)
}

function Test-LocalGitRepo {
    param([string]$RepoDir)
    return Test-Path (Join-Path $RepoDir ".git")
}

# 执行 git 子命令：合并 stdout/stderr，避免 informational 输出触发 Stop
function Invoke-GitInRepo {
    param(
        [string]$RepoDir,
        [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
        [string[]]$GitArgs
    )
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        $output = & git -C $RepoDir @GitArgs 2>&1
        $code = $LASTEXITCODE
        return @{
            exit_code = $code
            output    = @($output | ForEach-Object { "$_" })
        }
    } finally {
        $ErrorActionPreference = $prevEap
    }
}

# 检查工作区是否干净（含未跟踪文件）
function Get-WorkingTreeCheck {
    param([string]$RepoDir)
    if (-not (Test-LocalGitRepo -RepoDir $RepoDir)) {
        return @{
            ok      = $false
            clean   = $false
            reason  = "not_a_git_repo"
            details = @("本地无 .git 目录，请先使用 gitlab_group_clone.ps1 clone")
        }
    }
    $st = Invoke-GitInRepo -RepoDir $RepoDir status --porcelain
    if ($st.exit_code -ne 0) {
        return @{
            ok      = $false
            clean   = $false
            reason  = "git_status_failed"
            details = $st.output
        }
    }
    $dirtyLines = @($st.output | Where-Object { $_ -match '\S' })
    if ($dirtyLines.Count -gt 0) {
        return @{
            ok      = $false
            clean   = $false
            reason  = "uncommitted_changes"
            details = $dirtyLines
        }
    }
    return @{
        ok     = $true
        clean  = $true
        reason = "clean"
        details = @()
    }
}

function Get-CurrentBranchName {
    param([string]$RepoDir)
    $r = Invoke-GitInRepo -RepoDir $RepoDir rev-parse --abbrev-ref HEAD
    if ($r.exit_code -ne 0) { return "" }
    return ($r.output | Select-Object -Last 1).Trim()
}

# 单个仓库：fetch -> checkout -> pull（仅当 origin/分支 存在时 pull）
function Invoke-SingleRepoCheckout {
    param(
        [string]$RepoDir,
        [string]$BranchName,
        [string]$ProjectName,
        [string]$GroupPath
    )
    Write-Host "  [FETCH] origin $BranchName @ $RepoDir"
    $fetch = Invoke-GitInRepo -RepoDir $RepoDir fetch --quiet origin $BranchName
    foreach ($line in $fetch.output) { if ($line) { Write-Host "    $line" } }
    if ($fetch.exit_code -ne 0) {
        $fetchAll = Invoke-GitInRepo -RepoDir $RepoDir fetch --quiet origin
        foreach ($line in $fetchAll.output) { if ($line) { Write-Host "    $line" } }
    }

    $hasRemote = $false
    $revRemote = Invoke-GitInRepo -RepoDir $RepoDir rev-parse --verify "origin/$BranchName"
    if ($revRemote.exit_code -eq 0) { $hasRemote = $true }

    $beforeBranch = Get-CurrentBranchName -RepoDir $RepoDir
    $checkoutMode = ""

    if ($hasRemote) {
        Write-Host "  [CHECKOUT] $BranchName <- origin/$BranchName"
        $co = Invoke-GitInRepo -RepoDir $RepoDir checkout -B $BranchName "origin/$BranchName"
        foreach ($line in $co.output) { if ($line) { Write-Host "    $line" } }
        if ($co.exit_code -ne 0) {
            return @{
                ok            = $false
                status        = "checkout_failed"
                before_branch = $beforeBranch
                after_branch  = Get-CurrentBranchName -RepoDir $RepoDir
                remote_branch = $true
                pulled        = $false
                message       = "checkout 失败"
            }
        }
        $checkoutMode = "track_remote"
        Write-Host "  [PULL] origin $BranchName"
        $pull = Invoke-GitInRepo -RepoDir $RepoDir pull --quiet origin $BranchName
        foreach ($line in $pull.output) { if ($line) { Write-Host "    $line" } }
        $pullOk = ($pull.exit_code -eq 0)
        return @{
            ok            = $pullOk
            status        = if ($pullOk) { "success" } else { "pull_failed" }
            before_branch = $beforeBranch
            after_branch  = Get-CurrentBranchName -RepoDir $RepoDir
            remote_branch = $true
            pulled        = $pullOk
            checkout_mode = $checkoutMode
            message       = if ($pullOk) { "ok" } else { "pull 失败" }
        }
    }

    # 远端无目标分支：仅尝试切换本地已有分支
    $revLocal = Invoke-GitInRepo -RepoDir $RepoDir rev-parse --verify $BranchName
    if ($revLocal.exit_code -eq 0) {
        Write-Host "  [CHECKOUT] 本地分支 $BranchName（远端无 origin/$BranchName，跳过 pull）" -ForegroundColor Yellow
        $coLocal = Invoke-GitInRepo -RepoDir $RepoDir checkout $BranchName
        foreach ($line in $coLocal.output) { if ($line) { Write-Host "    $line" } }
        if ($coLocal.exit_code -ne 0) {
            return @{
                ok            = $false
                status        = "checkout_failed"
                before_branch = $beforeBranch
                after_branch  = Get-CurrentBranchName -RepoDir $RepoDir
                remote_branch = $false
                pulled        = $false
                message       = "本地 checkout 失败"
            }
        }
        return @{
            ok            = $true
            status        = "local_only"
            before_branch = $beforeBranch
            after_branch  = Get-CurrentBranchName -RepoDir $RepoDir
            remote_branch = $false
            pulled        = $false
            checkout_mode = "local_only"
            message       = "远端无 origin/$BranchName，仅切换本地分支"
        }
    }

    return @{
        ok            = $false
        status        = "branch_not_found"
        before_branch = $beforeBranch
        after_branch  = $beforeBranch
        remote_branch = $false
        pulled        = $false
        message       = "本地与远端均无分支 $BranchName"
    }
}

# ---------- 主流程 ----------
$projects = @(Resolve-ProjectNames -Names $ProjectNames -ListFile $ProjectListFile)
if ($projects.Count -eq 0) {
    throw "请通过 -ProjectNames 或 -ProjectListFile 指定至少一个项目名"
}

Write-Host "=== 批量 checkout 预检 ===" -ForegroundColor Cyan
Write-Host "Group: $TargetGroupPath"
Write-Host "分支: $Branch"
Write-Host "项目数: $($projects.Count)"
Write-Host "本地根目录: $DownloadRoot"
Write-Host ""

$targets = @()
foreach ($proj in $projects) {
    $repoDir = Get-SafeRepoDirectory -GroupPath $TargetGroupPath -ProjectName $proj
    $check = Get-WorkingTreeCheck -RepoDir $repoDir
    $targets += [pscustomobject]@{
        project_name = $proj
        project_path = "$TargetGroupPath/$proj"
        local_dir    = $repoDir
        preflight    = $check
    }
    $flag = if ($check.clean) { "OK" } else { "FAIL" }
    Write-Host ("[{0}] {1,-30} {2}" -f $flag, $proj, $repoDir)
    if (-not $check.clean) {
        foreach ($line in $check.details) {
            Write-Host "       $line" -ForegroundColor Yellow
        }
    }
}

$blocked = @($targets | Where-Object { -not $_.preflight.clean })
if ($blocked.Count -gt 0) {
    Write-Host ""
    Write-Host "预检失败：以下 $($blocked.Count) 个仓库不可操作，已中断（未执行任何 checkout）。" -ForegroundColor Red
    foreach ($b in $blocked) {
        $reason = $b.preflight.reason
        Write-Host "  - $($b.project_path) [$reason]" -ForegroundColor Red
        if ($reason -eq "uncommitted_changes") {
            Write-Host "    请先 commit / stash / 还原变更后再运行本脚本。" -ForegroundColor Yellow
        }
        if ($reason -eq "not_a_git_repo") {
            Write-Host "    请先运行 gitlab_group_clone.ps1 clone 该项目。" -ForegroundColor Yellow
        }
    }
    exit 1
}

Write-Host ""
Write-Host "预检通过，开始批量 checkout..." -ForegroundColor Green
Write-Host ""

$stamp = Get-Date -Format "yyyy-MM-ddTHHmmss"
$results = @()
$failCount = 0

foreach ($t in $targets) {
    Write-Host ">>> $($t.project_path)" -ForegroundColor Cyan
    $r = Invoke-SingleRepoCheckout -RepoDir $t.local_dir -BranchName $Branch `
        -ProjectName $t.project_name -GroupPath $TargetGroupPath
    $record = [pscustomobject]@{
        project_name  = $t.project_name
        project_path  = $t.project_path
        local_dir     = $t.local_dir
        branch        = $Branch
        status        = $r.status
        ok            = [bool]$r.ok
        before_branch = $r.before_branch
        after_branch  = $r.after_branch
        remote_branch = [bool]$r.remote_branch
        pulled        = [bool]$r.pulled
        message       = $r.message
        timestamp     = (Get-Date -Format "o")
    }
    $results += $record
    if (-not $r.ok) { $failCount++ }
    Write-Host ""
}

$safeGroup = $TargetGroupPath -replace "/", "_"
$reportPath = Join-Path $ReportDir "batch_checkout_${safeGroup}_${stamp}.json"
$report = [pscustomobject]@{
    group_path   = $TargetGroupPath
    branch       = $Branch
    download_root = $DownloadRoot
    stamp        = $stamp
    total        = $results.Count
    success      = @($results | Where-Object { $_.ok })
    failed       = @($results | Where-Object { -not $_.ok })
    all          = $results
}
Write-JsonFile -Path $reportPath -Object $report

$okCount = $results.Count - $failCount
Write-Host "完成：成功 $okCount / 失败 $failCount / 共 $($results.Count)" -ForegroundColor $(if ($failCount -eq 0) { "Green" } else { "Yellow" })
Write-Host "报告: $reportPath"

if ($failCount -gt 0) {
    Write-Host ""
    Write-Host "失败项目:" -ForegroundColor Red
    $results | Where-Object { -not $_.ok } | ForEach-Object {
        Write-Host "  $($_.project_path): $($_.message)"
    }
    exit 1
}

Write-Host ""
Write-Host "脚本执行完毕。" -ForegroundColor Green

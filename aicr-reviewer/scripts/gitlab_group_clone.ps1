#requires -Version 5.1
<#
.SYNOPSIS
    按 GitLab Group 分批克隆项目到本地 Windows 目录（默认 D:\agit）。

.DESCRIPTION
    从 ~/.opencodereview/config.json 读取 GitLab 配置（url 与 api_token），
    支持两种运行模式：
    1) GroupSummary：列出当前 token 可访问的 Group 清单及其项目数量，并导出 CSV/JSON 报告。
    2) BatchClone：针对指定 Group（默认 aulton-ms-basics）按分页批次克隆项目。

.PARAMETER Mode
    GroupSummary | BatchClone。默认 GroupSummary。

.PARAMETER GitLabUrl
    显式指定 GitLab URL；未指定时从 config.json 读取，兜底 https://gitlab.aulton.com。

.PARAMETER ApiToken
    显式指定 GitLab PAT；未指定时从 config.json 读取（兼容 gitlab.api_token / auth_token）。

.PARAMETER ConfigPath
    显式指定 .opencodereview/config.json 路径；未指定时使用 $HOME/.opencodereview/config.json。

.PARAMETER TargetGroupPath
    BatchClone 模式的目标 Group 路径（默认 aulton-ms-basics）。

.PARAMETER BatchSize
    每批克隆的项目数（默认 20）。

.PARAMETER BatchIndex
    从 0 开始的批次索引（默认 0）。

.PARAMETER IncludeSubgroups
    统计项目数与克隆时是否包含子组项目（默认开启）。

.PARAMETER UpdateExisting
    如果目标目录已存在仓库，则执行 git pull 而非跳过（默认关闭）。

.PARAMETER DownloadRoot
    下载根目录（默认 D:\agit）。

.EXAMPLE
    # 仅汇总所有分组及项目数
    .\scripts\gitlab_group_clone.ps1

    # 仅列出目标组的项目而不克隆（BatchSize=0）
    .\scripts\gitlab_group_clone.ps1 -Mode BatchClone -TargetGroupPath aulton-ms-basics -BatchSize 0

    # 克隆 aulton-ms-basics 第 0 批（每批 20 个）
    .\scripts\gitlab_group_clone.ps1 -Mode BatchClone -BatchIndex 0
#>
param(
    [ValidateSet("GroupSummary", "BatchClone")]
    [string]$Mode = "GroupSummary",
    [string]$GitLabUrl = "",
    [string]$ApiToken = "",
    [string]$ConfigPath = "",
    [string]$TargetGroupPath = "aulton-ms-basics",
    [int]$BatchSize = 20,
    [int]$BatchIndex = 0,
    [switch]$IncludeSubgroups = $true,
    [switch]$UpdateExisting,
    [string]$DownloadRoot = "D:\agit"
)

$ErrorActionPreference = "Stop"

# 参数校验
if ($BatchSize -lt 0) { throw "BatchSize 不能为负数" }
if ($BatchIndex -lt 0) { throw "BatchIndex 不能为负数" }
if (-not $DownloadRoot) { throw "DownloadRoot 不能为空" }

# 工具函数：写入 UTF-8 无 BOM 文件
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false
function Write-TextFile {
    param([string]$Path, [string]$Text)
    [System.IO.File]::WriteAllText($Path, $Text, $Utf8NoBom)
}

function Write-JsonFile {
    param([string]$Path, [object]$Object)
    Write-TextFile -Path $Path -Text ($Object | ConvertTo-Json -Depth 10)
}

# 读取 .opencodereview/config.json 中的 GitLab 配置
function Read-GitLabConfig {
    param([string]$ExplicitPath)

    $paths = @()
    if ($ExplicitPath) {
        $paths += (Resolve-Path $ExplicitPath -ErrorAction SilentlyContinue)
    }
    # 默认用户目录配置（Windows 与 Linux 均兼容）
    $paths += Join-Path $HOME ".opencodereview" "config.json"

    foreach ($p in $paths) {
        if (-not $p) { continue }
        if (Test-Path $p) {
            try {
                $raw = Get-Content $p -Raw -Encoding UTF8
                return ($raw | ConvertFrom-Json)
            } catch {
                Write-Warning "配置文件存在但解析失败: $p"
            }
        }
    }
    return $null
}

function Get-GitLabToken {
    param([object]$Config)
    if (-not $Config) { return "" }
    $gitlab = $Config.gitlab
    if ($gitlab) {
        # 优先读取 api_token，兼容 auth_token 兜底
        if ($gitlab.api_token) { return $gitlab.api_token }
        if ($gitlab.auth_token) { return $gitlab.auth_token }
    }
    # 兼容旧版顶层字段
    if ($Config.gitlab_api_token) { return $Config.gitlab_api_token }
    return ""
}

function Get-GitLabUrl {
    param([object]$Config)
    if ($Config -and $Config.gitlab -and $Config.gitlab.url) {
        return ($Config.gitlab.url -replace "/+$", "")
    }
    return "https://gitlab.aulton.com"
}

# 初始化配置：命令行参数优先级最高，其次是配置文件，最后是默认值
$Config = Read-GitLabConfig -ExplicitPath $ConfigPath
if (-not $Config) {
    throw "未找到 .opencodereview/config.json；请指定 -ConfigPath 或创建 $HOME\.opencodereview\config.json"
}

$ResolvedToken = if ($ApiToken) { $ApiToken } else { Get-GitLabToken -Config $Config }
$ResolvedUrl   = if ($GitLabUrl) { ($GitLabUrl -replace "/+$", "") } else { Get-GitLabUrl -Config $Config }

if (-not $ResolvedToken) {
    throw "未在配置中找到 gitlab.api_token（或 auth_token），且未通过 -ApiToken 传入。"
}
if (-not $ResolvedUrl) {
    throw "未解析到有效的 GitLab URL。"
}

# 报告输出目录：固定放在下载根目录下的 _reports，便于后续分批重跑
$ReportDir = Join-Path $DownloadRoot "_reports"
New-Item -ItemType Directory -Path $ReportDir -Force | Out-Null

$Headers = @{
    "PRIVATE-TOKEN" = $ResolvedToken
    "Content-Type"  = "application/json"
}

# 通用 GitLab API GET 请求，带分页与重试
function Invoke-PageList {
    param(
        [string]$Endpoint,
        [hashtable]$Query = @{}
    )
    $perPage = 100
    $page = 1
    $all = @()

    # 构建基础 URL：Endpoint 支持已编码或未编码的 group path
    $baseUrl = "$ResolvedUrl/api/v4/$Endpoint"

    while ($true) {
        $q = @{ page = $page; per_page = $perPage }
        foreach ($k in $Query.Keys) { $q[$k] = $Query[$k] }
        $qs = ($q.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "&"
        $url = "$baseUrl`?$qs"

        $attempt = 0
        $maxAttempts = 3
        $done = $false
        while ($attempt -lt $maxAttempts -and -not $done) {
            try {
                $resp = Invoke-RestMethod -Uri $url -Headers $Headers -Method GET -UseBasicParsing -TimeoutSec 60
                $done = $true
            } catch {
                $attempt++
                if ($attempt -ge $maxAttempts) { throw }
                Write-Warning "请求失败（第 $attempt 次重试）: $url`n$_"
                Start-Sleep -Seconds (2 * $attempt)
            }
        }

        if (-not $resp) { break }
        $all += $resp
        if ($resp.Count -lt $perPage) { break }
        $page++
    }
    return $all
}

function Get-GroupIdByPath {
    param([string]$GroupPath)
    # 对 group path 进行 URL 编码，处理子组路径中的 "/"
    $encoded = [System.Uri]::EscapeDataString($GroupPath)
    $url = "$ResolvedUrl/api/v4/groups/$encoded"
    try {
        $group = Invoke-RestMethod -Uri $url -Headers $Headers -Method GET -UseBasicParsing -TimeoutSec 60
        return $group.id
    } catch {
        throw "无法获取 Group [$GroupPath] 信息，请检查路径或 token 权限。URL: $url"
    }
}

function Get-GroupProjectCount {
    param([string]$GroupId, [bool]$WithSubgroups)
    $q = @{}
    if ($WithSubgroups) { $q["include_subgroups"] = "true" }
    $projects = Invoke-PageList -Endpoint "groups/$GroupId/projects" -Query $q
    return $projects.Count
}

function Get-GroupProjects {
    param([string]$GroupId, [bool]$WithSubgroups)
    $q = @{
        order_by = "path"
        sort     = "asc"
    }
    if ($WithSubgroups) { $q["include_subgroups"] = "true" }
    $projects = Invoke-PageList -Endpoint "groups/$GroupId/projects" -Query $q
    # 按 path_with_namespace 稳定排序，确保批次可重跑
    return ($projects | Sort-Object path_with_namespace)
}

function Format-DateStamp {
    return (Get-Date -Format "yyyy-MM-ddTHHmmss")
}

# 安全转换本地目录名，避免 Windows 保留字符与过长路径
function Get-SafeRepoDirectory {
    param([string]$GroupPath, [string]$ProjectName)
    # 将 group path 中的 "/" 转换为本地目录层级
    $parts = $GroupPath -split "/"
    $safeParts = $parts | ForEach-Object {
        # 移除 Windows 路径非法字符
        $_ -replace '[\\/:*?"<>|]', '_'
    }
    $safeProjectName = $ProjectName -replace '[\\/:*?"<>|]', '_'
    return Join-Path $DownloadRoot (Join-Path ($safeParts -join "\") $safeProjectName)
}

function Invoke-CloneOrUpdateRepo {
    param(
        [string]$CloneUrl,
        [string]$RepoDir,
        [bool]$UpdateExisting
    )
    if (Test-Path (Join-Path $RepoDir ".git")) {
        if ($UpdateExisting) {
            Write-Host "  [UPDATE] $RepoDir"
            & git -C $RepoDir pull --quiet 2>&1 | ForEach-Object { Write-Host "    $_" }
            return $LASTEXITCODE -eq 0
        } else {
            Write-Host "  [SKIP] 已存在: $RepoDir"
            return $true
        }
    }
    New-Item -ItemType Directory -Path $RepoDir -Force | Out-Null
    Write-Host "  [CLONE] $CloneUrl -> $RepoDir"
    & git clone --quiet $CloneUrl $RepoDir 2>&1 | ForEach-Object { Write-Host "    $_" }
    return $LASTEXITCODE -eq 0
}

# 模式 1：GroupSummary — 汇总所有可访问 Group 及其项目数
function Start-GroupSummary {
    Write-Host "=== 获取 Group 列表及项目数 ===" -ForegroundColor Cyan
    Write-Host "GitLab URL: $ResolvedUrl"
    Write-Host "包含子组: $IncludeSubgroups"

    $groups = Invoke-PageList -Endpoint "groups" -Query @{ all_available = "true"; min_access_level = 20 }
    if (-not $groups) {
        Write-Host "未获取到任何 Group，请检查 token 权限。" -ForegroundColor Yellow
        return
    }

    $rows = @()
    foreach ($g in ($groups | Sort-Object full_path)) {
        $count = 0
        try {
            $count = Get-GroupProjectCount -GroupId $g.id -WithSubgroups $IncludeSubgroups
        } catch {
            Write-Warning "统计 Group [$($g.full_path)] 项目数失败: $_"
        }
        $rows += [pscustomobject]@{
            group_id     = $g.id
            group_path   = $g.full_path
            group_name   = $g.name
            project_count = $count
        }
        Write-Host ("{0,6} | {1,-40} | {2,8} 个项目" -f $g.id, $g.full_path, $count)
    }

    $stamp = Format-DateStamp
    $csvPath = Join-Path $ReportDir "group_project_summary_${stamp}.csv"
    $jsonPath = Join-Path $ReportDir "group_project_summary_${stamp}.json"

    $rows | Export-Csv -Path $csvPath -NoTypeInformation -Encoding UTF8
    Write-JsonFile -Path $jsonPath -Object $rows

    Write-Host ""
    Write-Host "汇总完成：共 $($groups.Count) 个 Group，总项目数 $($rows | Measure-Object -Property project_count -Sum | Select-Object -ExpandProperty Sum)" -ForegroundColor Green
    Write-Host "CSV 报告: $csvPath"
    Write-Host "JSON 报告: $jsonPath"
}

# 模式 2：BatchClone — 针对指定 Group 分批克隆
function Start-BatchClone {
    param([string]$GroupPath)
    Write-Host "=== 按 Group 分批克隆 ===" -ForegroundColor Cyan
    Write-Host "目标 Group: $GroupPath"
    Write-Host "批次大小: $BatchSize, 批次索引: $BatchIndex, 包含子组: $IncludeSubgroups"

    $groupId = Get-GroupIdByPath -GroupPath $GroupPath
    Write-Host "Group ID: $groupId"

    $allProjects = Get-GroupProjects -GroupId $groupId -WithSubgroups $IncludeSubgroups
    $total = $allProjects.Count
    Write-Host "该组共有 $total 个项目"

    if ($BatchSize -le 0) {
        Write-Host "BatchSize <= 0，仅列出项目，不执行克隆。" -ForegroundColor Yellow
        $allProjects | ForEach-Object { Write-Host "  $($_.path_with_namespace)" }
        return
    }

    $start = $BatchIndex * $BatchSize
    if ($start -ge $total) {
        Write-Host "批次索引 $BatchIndex 超出范围（共 $total 个项目，每批 $BatchSize 个）。" -ForegroundColor Yellow
        return
    }
    $end = [Math]::Min($start + $BatchSize - 1, $total - 1)
    $batchProjects = $allProjects[$start..$end]

    Write-Host "本批处理: 第 $($start + 1) - $($end + 1) 个，共 $($batchProjects.Count) 个"

    $successList = @()
    $skipList = @()
    $failList = @()
    $stamp = Format-DateStamp

    foreach ($p in $batchProjects) {
        $cloneUrl = $p.http_url_to_repo
        if (-not $cloneUrl) {
            $cloneUrl = $p.web_url + ".git"
        }
        $repoDir = Get-SafeRepoDirectory -GroupPath $p.namespace.full_path -ProjectName $p.path
        $hasGit = Test-Path (Join-Path $repoDir ".git")
        $cloneOk = $false
        $status = "failed"
        try {
            if ($hasGit -and -not $UpdateExisting) {
                # 默认策略：已存在仓库直接跳过，不进入 git 操作
                Write-Host "  [SKIP] 已存在: $repoDir"
                $cloneOk = $true
                $status = "skipped"
            } else {
                $cloneOk = Invoke-CloneOrUpdateRepo -CloneUrl $cloneUrl -RepoDir $repoDir -UpdateExisting $UpdateExisting
                $status = if ($hasGit) { "updated" } else { "success" }
            }
        } catch {
            Write-Warning "克隆失败: $cloneUrl`n$_"
            $cloneOk = $false
            $status = "failed"
        }

        $record = [pscustomobject]@{
            project_id          = $p.id
            project_path        = $p.path_with_namespace
            clone_url           = $cloneUrl
            local_dir           = $repoDir
            status              = $status
            timestamp           = (Get-Date -Format "o")
        }

        if ($cloneOk) {
            if ($status -eq "skipped") {
                $skipList += $record
            } else {
                $successList += $record
            }
        } else {
            $failList += $record
        }
    }

    $report = [pscustomobject]@{
        group_path   = $GroupPath
        group_id     = $groupId
        batch_index  = $BatchIndex
        batch_size   = $BatchSize
        total_projects = $total
        start_index  = $start
        end_index    = $end
        stamp        = $stamp
        success      = $successList
        skipped      = $skipList
        failed       = $failList
    }

    # 将 group path 中的 "/" 替换为 "_"，避免文件名出现非法路径分隔符
    $safeGroupName = $GroupPath -replace "/", "_"
    $jsonPath = Join-Path $ReportDir "batch_clone_${safeGroupName}_${BatchIndex}_${stamp}.json"
    Write-JsonFile -Path $jsonPath -Object $report

    Write-Host ""
    Write-Host "本批完成：成功 $($successList.Count) / 跳过 $($skipList.Count) / 失败 $($failList.Count)" -ForegroundColor Green
    Write-Host "批次报告: $jsonPath"

    if ($failList.Count -gt 0) {
        Write-Host ""
        Write-Host "失败项目:" -ForegroundColor Red
        $failList | ForEach-Object { Write-Host "  $($_.project_path) -> $($_.local_dir)" }
    }
}

# 主入口
switch ($Mode) {
    "GroupSummary" { Start-GroupSummary }
    "BatchClone"   { Start-BatchClone -GroupPath $TargetGroupPath }
    default { throw "未知模式: $Mode" }
}

Write-Host ""
Write-Host "脚本执行完毕。" -ForegroundColor Green

#requires -Version 5.1
# 编码：须保存为 UTF-8 BOM；无 BOM 时 Windows PowerShell 5.1 会把中文乱码导致语法错误。
<#
.SYNOPSIS
    按 GitLab Group 分批克隆项目到本地 Windows 目录（默认 D:\agit）。

.DESCRIPTION
    从 ~/.opencodereview/config.json 读取 GitLab 配置（url 与 api_token），
    支持两种运行模式：
    1) GroupSummary：列出当前 token 可访问的 Group 清单及其项目数量，并导出 CSV/JSON 报告。
    2) BatchClone：针对一个或多个指定 Group 按分页批次克隆项目。

.PARAMETER Mode
    GroupSummary | BatchClone。默认 GroupSummary。

.PARAMETER GitLabUrl
    显式指定 GitLab URL；未指定时从 config.json 读取，兜底 https://gitlab.aulton.com。

.PARAMETER ApiToken
    显式指定 GitLab PAT；未指定时从 config.json 读取（兼容 gitlab.api_token / auth_token）。

.PARAMETER ConfigPath
    显式指定 .opencodereview/config.json 路径；未指定时使用 $HOME/.opencodereview/config.json。

.PARAMETER TargetGroupPath
    BatchClone 的目标 Group 路径，可传单个、多个或逗号分隔字符串（默认 aulton-ms-basics）。

.PARAMETER TargetGroupListFile
    BatchClone 可选：从文本文件读取 Group 路径，每行一个；# 开头为注释。可与 -TargetGroupPath 合并去重。

.PARAMETER BatchSize
    每批克隆的项目数（默认 20）。

.PARAMETER BatchIndex
    从 0 开始的批次索引（默认 0）。

.PARAMETER IncludeSubgroups
    统计项目数与克隆时是否包含子组项目（默认开启）。

.PARAMETER UpdateExisting
    如果目标目录已存在仓库，则执行 git pull 而非跳过（默认关闭）。与 -SkipExisting 互斥优先：开启本项时会更新而非跳过。

.PARAMETER SkipExisting
    本地目录已存在 git 仓库（含 .git）时跳过 clone（默认 $true）。
    判定规则：D:\agit\<group>\<project>\.git 存在即视为已 clone。
    关闭：-SkipExisting:$false（目录已有仓库时会报错，不会强制覆盖）。

.PARAMETER CheckoutRelease
    克隆/更新成功后是否切换到 release 分支（默认 $true）。关闭：-CheckoutRelease:$false

.PARAMETER ReleaseBranch
    与 -CheckoutRelease 配合使用的分支名（默认 release）。

.PARAMETER MinAccessLevel
    GroupSummary 可选：仅列出当前用户在该 Group 内达到指定 access level 的分组
    （10=Guest, 20=Reporter, 30=Developer…）。默认 0 表示不过滤。
    注意：若只在项目级有权限、组级为 Guest，设置 20 会导致列表为空。

.PARAMETER DownloadRoot
    下载根目录（默认 D:\agit）。

.EXAMPLE
    # 仅汇总所有分组及项目数
    .\scripts\gitlab_group_clone.ps1

    # 仅列出目标组的项目而不克隆（BatchSize=0）
    .\scripts\gitlab_group_clone.ps1 -Mode BatchClone -TargetGroupPath aulton-ms-basics -BatchSize 0

    # 仅列出多个目标组的项目而不克隆
    .\scripts\gitlab_group_clone.ps1 -Mode BatchClone -TargetGroupPath aulton-ms-basics,aulton-ms-finance -BatchSize 0

    # 克隆多个 Group 各自的第 0 批（每批 20 个）
    .\scripts\gitlab_group_clone.ps1 -Mode BatchClone -TargetGroupPath @('aulton-ms-basics','aulton-ms-finance') -BatchIndex 0

    # 从文件读取 Group 列表并克隆（每行一个 group path）
    .\scripts\gitlab_group_clone.ps1 -Mode BatchClone -TargetGroupListFile D:\agit\groups.txt -BatchIndex 0
#>
param(
    [ValidateSet("GroupSummary", "BatchClone")]
    [string]$Mode = "GroupSummary",
    [string]$GitLabUrl = "",
    [string]$ApiToken = "",
    [string]$ConfigPath = "",
    [string[]]$TargetGroupPath = @("aulton-ms-basics"),
    [string]$TargetGroupListFile = "",
    [int]$BatchSize = 20,
    [int]$BatchIndex = 0,
    [switch]$IncludeSubgroups = $true,
    [switch]$UpdateExisting,
    [bool]$SkipExisting = $true,
    [bool]$CheckoutRelease = $true,
    [string]$ReleaseBranch = "release",
    [int]$MinAccessLevel = 0,
    [string]$DownloadRoot = "D:\agit"
)

$ErrorActionPreference = "Stop"

# 参数校验
if ($BatchSize -lt 0) { throw "BatchSize 不能为负数" }
if ($BatchIndex -lt 0) { throw "BatchIndex 不能为负数" }
if (-not $DownloadRoot) { throw "DownloadRoot 不能为空" }
if (-not $ReleaseBranch) { throw "ReleaseBranch 不能为空" }

# 解析 BatchClone 目标 Group：支持数组、逗号分隔、以及外部列表文件
function Resolve-TargetGroupPaths {
    param(
        [string[]]$Paths,
        [string]$ListFile
    )
    $result = @()
    foreach ($raw in $Paths) {
        if (-not $raw) { continue }
        # 允许 "group-a,group-b" 写在同一个参数里
        foreach ($part in ($raw -split ",")) {
            $trimmed = $part.Trim().Trim("/")
            if ($trimmed) { $result += $trimmed }
        }
    }
    if ($ListFile) {
        if (-not (Test-Path $ListFile)) {
            throw "TargetGroupListFile 不存在: $ListFile"
        }
        Get-Content $ListFile -Encoding UTF8 | ForEach-Object {
            $line = $_.Trim()
            if (-not $line -or $line.StartsWith("#")) { return }
            $result += $line.Trim("/")
        }
    }
    # 去重且保持顺序；强制返回数组，避免单元素时被 PS 解包成标量（StrictMode 下 .Count 报错）
    $unique = @()
    foreach ($g in $result) {
        if ($unique -notcontains $g) { $unique += $g }
    }
    return [string[]]@($unique)
}

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
    # 默认用户目录配置（PS 5.1 的 Join-Path 仅支持两段路径，需嵌套拼接）
    $paths += Join-Path (Join-Path $HOME ".opencodereview") "config.json"

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
        # 单条记录时 Invoke-RestMethod 可能返回对象而非数组，统一包装
        $all += @($resp)
        if (@($resp).Count -lt $perPage) { break }
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
    return @($projects).Count
}

function Get-GroupProjects {
    param([string]$GroupId, [bool]$WithSubgroups)
    $q = @{
        order_by = "path"
        sort     = "asc"
    }
    if ($WithSubgroups) { $q["include_subgroups"] = "true" }
    $projects = Invoke-PageList -Endpoint "groups/$GroupId/projects" -Query $q
    # 强制数组，避免仅 1 个项目时返回标量导致后续 .Count 失败
    return @($projects | Sort-Object path_with_namespace)
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

# 判断本地是否已 clone：以 .git 目录为准（比仅看文件夹名更可靠）
function Test-LocalGitRepo {
    param([string]$RepoDir)
    return Test-Path (Join-Path $RepoDir ".git")
}

function Invoke-CloneOrUpdateRepo {
    param(
        [string]$CloneUrl,
        [string]$RepoDir,
        [bool]$UpdateExisting,
        [bool]$SkipExisting
    )
    if (Test-LocalGitRepo -RepoDir $RepoDir) {
        if ($UpdateExisting) {
            Write-Host "  [UPDATE] $RepoDir"
            & git -C $RepoDir pull --quiet 2>&1 | ForEach-Object { Write-Host "    $_" }
            return @{
                ok     = ($LASTEXITCODE -eq 0)
                status = "updated"
            }
        }
        if ($SkipExisting) {
            Write-Host "  [SKIP] 已存在: $RepoDir"
            return @{
                ok     = $true
                status = "skipped"
            }
        }
        throw "目录已是 git 仓库，且未启用 -UpdateExisting；若要跳过请保持默认 -SkipExisting，或加 -UpdateExisting 拉取更新。路径: $RepoDir"
    }
    # 非空目录但无 .git：可能是上次 clone 失败残留，避免 git clone 报错
    if (Test-Path $RepoDir) {
        $itemCount = @(Get-ChildItem -LiteralPath $RepoDir -Force -ErrorAction SilentlyContinue).Count
        if ($itemCount -gt 0) {
            Write-Warning "  [WARN] 目录非空且无 .git，跳过以免覆盖: $RepoDir"
            return @{
                ok     = $false
                status = "failed"
            }
        }
    }
    New-Item -ItemType Directory -Path $RepoDir -Force | Out-Null
    Write-Host "  [CLONE] $CloneUrl -> $RepoDir"
    & git clone --quiet $CloneUrl $RepoDir 2>&1 | ForEach-Object { Write-Host "    $_" }
    return @{
        ok     = ($LASTEXITCODE -eq 0)
        status = "success"
    }
}

# 克隆/更新后切换到指定 release 分支（默认 release）；远端无该分支时仅警告，不中断整批
function Invoke-CheckoutReleaseBranch {
    param(
        [string]$RepoDir,
        [string]$BranchName
    )
    if (-not (Test-Path (Join-Path $RepoDir ".git"))) {
        Write-Warning "  [CHECKOUT] 非 git 仓库，跳过: $RepoDir"
        return $false
    }
    Write-Host "  [CHECKOUT] $BranchName @ $RepoDir"
    # 尽量只 fetch 目标分支，减少大仓库耗时
    & git -C $RepoDir fetch --quiet origin $BranchName 2>&1 | ForEach-Object { Write-Host "    $_" }
    if ($LASTEXITCODE -ne 0) {
        & git -C $RepoDir fetch --quiet origin 2>&1 | ForEach-Object { Write-Host "    $_" }
    }
    & git -C $RepoDir rev-parse --verify "origin/$BranchName" 2>&1 | Out-Null
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "  [CHECKOUT] 远端无 origin/$BranchName，保持当前分支"
        return $false
    }
    & git -C $RepoDir checkout -B $BranchName "origin/$BranchName" 2>&1 | ForEach-Object { Write-Host "    $_" }
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "  [CHECKOUT] 切换 $BranchName 失败"
        return $false
    }
    & git -C $RepoDir pull --quiet origin $BranchName 2>&1 | ForEach-Object { Write-Host "    $_" }
    return $true
}

# 模式 1：GroupSummary — 汇总所有可访问 Group 及其项目数
function Start-GroupSummary {
    Write-Host "=== 获取 Group 列表及项目数 ===" -ForegroundColor Cyan
    Write-Host "GitLab URL: $ResolvedUrl"
    Write-Host "包含子组: $IncludeSubgroups"
    if ($MinAccessLevel -gt 0) {
        Write-Host "最低组内权限: $MinAccessLevel（低于此级别的 Group 会被 API 过滤）" -ForegroundColor Yellow
    }

    # 校验 token 是否有效，便于区分「token 无效」与「确实无 Group」
    try {
        $me = Invoke-RestMethod -Uri "$ResolvedUrl/api/v4/user" -Headers $Headers -Method GET -UseBasicParsing -TimeoutSec 30
        Write-Host "当前用户: $($me.username) (id=$($me.id))"
    } catch {
        throw "GitLab token 无效或无法访问 $ResolvedUrl/api/v4/user，请检查 api_token 与网络。`n$_"
    }

    # 默认不过滤 min_access_level：很多账号仅在项目级有 Developer 权限、组级为 Guest
    $groupQuery = @{ all_available = "true" }
    if ($MinAccessLevel -gt 0) { $groupQuery["min_access_level"] = "$MinAccessLevel" }

    $groups = @(Invoke-PageList -Endpoint "groups" -Query $groupQuery)
    if ($groups.Count -eq 0) {
        Write-Host "未获取到任何 Group。" -ForegroundColor Yellow
        if ($MinAccessLevel -gt 0) {
            Write-Host "提示：已设置 -MinAccessLevel $MinAccessLevel，若组级权限不足会导致列表为空；可去掉该参数重试。" -ForegroundColor Yellow
        } else {
            Write-Host "请确认 token 拥有 read_api/api 权限，且账号至少加入了某个 Group 或可见公开 Group。" -ForegroundColor Yellow
        }
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
    Write-Host "跳过已存在: $SkipExisting, 更新已存在: $UpdateExisting, 切换 release: $CheckoutRelease, 分支名: $ReleaseBranch"

    $groupId = Get-GroupIdByPath -GroupPath $GroupPath
    Write-Host "Group ID: $groupId"

    $allProjects = @(Get-GroupProjects -GroupId $groupId -WithSubgroups $IncludeSubgroups)
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
        $cloneOk = $false
        $status = "failed"
        $checkoutOk = $null
        try {
            $cloneResult = Invoke-CloneOrUpdateRepo -CloneUrl $cloneUrl -RepoDir $repoDir `
                -UpdateExisting $UpdateExisting -SkipExisting $SkipExisting
            $cloneOk = [bool]$cloneResult.ok
            $status = [string]$cloneResult.status
            # 仓库可用且启用 CheckoutRelease 时，尝试切到 release 分支（含 skipped 的已存在仓库）
            if ($cloneOk -and $CheckoutRelease -and (Test-LocalGitRepo -RepoDir $repoDir)) {
                $checkoutOk = Invoke-CheckoutReleaseBranch -RepoDir $repoDir -BranchName $ReleaseBranch
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
            checkout_release    = [bool]$CheckoutRelease
            release_branch      = $ReleaseBranch
            checkout_ok         = $checkoutOk
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
        group_path       = $GroupPath
        group_id         = $groupId
        batch_index      = $BatchIndex
        batch_size       = $BatchSize
        total_projects   = $total
        start_index      = $start
        end_index        = $end
        checkout_release = [bool]$CheckoutRelease
        release_branch   = $ReleaseBranch
        skip_existing    = [bool]$SkipExisting
        stamp            = $stamp
        success          = $successList
        skipped          = $skipList
        failed           = $failList
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
    "BatchClone"   {
        # @() 再包一层，兼容 StrictMode 下对标量访问 .Count 报错
        $groupPaths = @(Resolve-TargetGroupPaths -Paths $TargetGroupPath -ListFile $TargetGroupListFile)
        if ($groupPaths.Count -eq 0) {
            throw "BatchClone 需要至少指定一个 Group：-TargetGroupPath 或 -TargetGroupListFile"
        }
        Write-Host "共 $($groupPaths.Count) 个目标 Group: $($groupPaths -join ', ')"
        foreach ($gp in $groupPaths) {
            if ($groupPaths.Count -gt 1) {
                Write-Host ""
                Write-Host "========== Group: $gp ==========" -ForegroundColor Magenta
            }
            Start-BatchClone -GroupPath $gp
        }
    }
    default { throw "未知模式: $Mode" }
}

Write-Host ""
Write-Host "脚本执行完毕。" -ForegroundColor Green

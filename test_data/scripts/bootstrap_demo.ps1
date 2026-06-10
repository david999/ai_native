# 校验 spring-cloud-demo 存在且 remote 指向本地 GitLab
$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$DemoDir = Join-Path $RepoRoot "test_data\spring-cloud-demo"
$GitLabUrl = if ($env:GITLAB_URL) { $env:GITLAB_URL } else { "http://localhost:8000" }

if (-not (Test-Path $DemoDir)) {
    throw "spring-cloud-demo not found at $DemoDir — clone from $GitLabUrl first"
}

Push-Location $DemoDir
try {
    $remote = (git remote get-url origin 2>$null)
    if (-not $remote) { throw "No git remote 'origin' in spring-cloud-demo" }
    if ($remote -notmatch "localhost:8000" -and $remote -notmatch ":8000") {
        Write-Warning "origin may not point to local GitLab: $remote"
    }
    Write-Host "OK demo remote: $remote"

    $base = git rev-parse --verify aicr-test-base 2>$null
    if (-not $base) {
        $current = git branch --show-current
        if (-not $current) { git checkout -B main 2>$null }
        git checkout -B aicr-test-base
        git push -u origin aicr-test-base 2>$null
        Write-Host "Created baseline branch aicr-test-base"
    } else {
        Write-Host "OK baseline branch aicr-test-base exists"
    }
} finally {
    Pop-Location
}

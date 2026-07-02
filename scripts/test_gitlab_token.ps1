# Test GitLab Access Token: scopes, role, accessible projects
# Usage:
#   [Environment]::SetEnvironmentVariable('gitlab_at', '<your-token>', 'User')
#   .\scripts\test_gitlab_token.ps1 -GitLabBaseUrl "https://gitlab.aulton.com"
# Note: Uses curl.exe to avoid PowerShell session cookie reuse.

param(
    [string]$GitLabBaseUrl = "https://gitlab.aulton.com",
    [int]$ProjectLimit = 50,
    [string]$ProbeProjectPath = "aulton-ms-finance/aulton-ms-pay-config",
    [int]$TimeoutSec = 20
)

$ErrorActionPreference = 'Continue'

$token = $null
$scopeUsed = $null
foreach ($s in @('User', 'Machine', 'Process')) {
    $v = [Environment]::GetEnvironmentVariable('gitlab_at', $s)
    if ($v -and -not $token) {
        $token = $v
        $scopeUsed = $s
    }
}

if (-not $token) {
    Write-Error "Environment variable gitlab_at not found. Set it first: [Environment]::SetEnvironmentVariable('gitlab_at', '<token>', 'User')"
    exit 1
}

$base = $GitLabBaseUrl.TrimEnd('/')

function Invoke-ApiCurl {
    param($Method, $Url, $Body = $null)
    try {
        if ($Body) {
            $output = curl.exe -s -m $TimeoutSec -X $Method -H "PRIVATE-TOKEN: $token" -H "Content-Type: application/json" -d $Body -w "`n__HTTP__%{http_code}" $Url
        } else {
            $output = curl.exe -s -m $TimeoutSec -X $Method -H "PRIVATE-TOKEN: $token" -w "`n__HTTP__%{http_code}" $Url
        }
        $lines = $output -split "`n"
        $httpLine = $lines | Where-Object { $_ -like '__HTTP__*' } | Select-Object -Last 1
        $status = [int]($httpLine -replace '__HTTP__', '')
        $bodyText = ($lines | Where-Object { $_ -notlike '__HTTP__*' }) -join "`n"
        return @{ Status = $status; Ok = $status -ge 200 -and $status -lt 300; Content = $bodyText }
    } catch {
        return @{ Status = 0; Ok = $false; Content = $_.Exception.Message }
    }
}

function Show-Section {
    param($title)
    Write-Host ''
    Write-Host "==== $title ===="
}

Write-Host "Target: $base"
$shortToken = $token.Substring(0, [Math]::Min(8, $token.Length))
Write-Host "Token source: $scopeUsed scope, prefix: $shortToken..., length: $($token.Length)"

Show-Section '1. Token owner (user)'
$u = Invoke-ApiCurl -Method 'GET' -Url "$base/api/v4/user"
if ($u.Ok) {
    $user = $u.Content | ConvertFrom-Json
    $user | Select-Object id, username, name, email, state, created_at | ConvertTo-Json -Depth 2
} else {
    Write-Host "HTTP $($u.Status) $($u.Content)"
    Write-Host 'Hint: API timeout or unreachable. Check network/VPN.'
}

Show-Section '2. Accessible projects (membership=true)'
$projects = @()
$query = "$base/api/v4/projects?membership=true&per_page=$ProjectLimit&order_by=last_activity_at&sort=desc"
$pg = Invoke-ApiCurl -Method 'GET' -Url $query
$probeProject = $null
if ($pg.Ok) {
    $projects = $pg.Content | ConvertFrom-Json
    Write-Host "accessible projects count: $($projects.Count)"
    foreach ($proj in $projects) {
        $level = '?'
        if ($proj.permissions.project_access) {
            $level = $proj.permissions.project_access.access_level
        }
        Write-Host "  id=$($proj.id) level=$level name=$($proj.path_with_namespace)"
        if (-not $probeProject -and $proj.path_with_namespace -eq $ProbeProjectPath) {
            $probeProject = $proj
        }
    }
} else {
    Write-Host "HTTP $($pg.Status) $($pg.Content)"
}

Show-Section '3. Scope inference (api write vs read_api)'
$hasApiWrite = $false
if ($probeProject) {
    $probeId = $probeProject.id
    # First unstar to ensure a clean state for the write test (ignore result)
    $null = Invoke-ApiCurl -Method 'POST' -Url "$base/api/v4/projects/$probeId/unstar"
    $star = Invoke-ApiCurl -Method 'POST' -Url "$base/api/v4/projects/$probeId/star"
    Write-Host "POST /projects/$probeId/star -> HTTP $($star.Status)"
    if ($star.Status -eq 201) {
        $hasApiWrite = $true
        Write-Host '=> token has **api** write scope (star created)'
    } elseif ($star.Status -eq 304) {
        $hasApiWrite = $true
        Write-Host '=> token has **api** write scope (project already starred)'
    } elseif ($star.Status -eq 401 -or $star.Status -eq 403) {
        Write-Host '=> token likely **read_api** only (no api write scope)'
    } else {
        Write-Host '=> cannot infer scope (unexpected response)'
    }
    # Cleanup: unstar after test
    $null = Invoke-ApiCurl -Method 'POST' -Url "$base/api/v4/projects/$probeId/unstar"
} else {
    Write-Host "Probe project '$ProbeProjectPath' not found in accessible list."
    Write-Host 'Skipping write scope test.'
}

Show-Section '4. read_repository test (git ls-remote)'
if ($probeProject) {
    $tmp = New-Item -ItemType Directory -Path "$env:TEMP\gittest_$(Get-Random)" -Force
    Push-Location $tmp
    try {
        $env:GIT_TERMINAL_PROMPT = '0'
        $hostPart = $base -replace '^https?://'
        $url = "http://oauth2:$token@$hostPart/$ProbeProjectPath.git"
        $out = git ls-remote $url HEAD 2>&1
        $exit = $LASTEXITCODE
        Write-Host "git ls-remote exit=$exit"
        Write-Host ($out | Out-String)
        $hasReadRepo = $exit -eq 0
    } finally {
        Pop-Location
        Remove-Item -Recurse -Force $tmp -ErrorAction SilentlyContinue
    }
} else {
    Write-Host 'No probe project, skip git ls-remote'
    $hasReadRepo = $false
}

Show-Section '5. Summary'
if ($user) {
    Write-Host "User: $($user.username) (id=$($user.id), name=$($user.name), state=$($user.state))"
} else {
    Write-Host 'User: cannot fetch (API timeout or invalid token)'
}
if ($probeProject) {
    $level = $probeProject.permissions.project_access.access_level
    Write-Host "Probe project role: $level (10=Guest, 20=Reporter, 30=Developer, 40=Maintainer, 50=Owner)"
}
Write-Host "api write scope: $hasApiWrite"
Write-Host "read_repository: $hasReadRepo"
Write-Host "accessible projects: $($projects.Count)"

Show-Section 'Access level reference'
Write-Host '10=Guest  20=Reporter  30=Developer  40=Maintainer  50=Owner'
Write-Host 'OCR Gateway minimum: Reporter(20) + api + read_repository to read MR and post comments.'

# Shared helpers for run_acceptance.ps1 (dot-sourced; do not run directly).

function Write-AcceptanceSubprocessLine {
    param([object]$Line)
    if ($Line -is [System.Management.Automation.ErrorRecord]) {
        Write-Host $Line.ToString() -ForegroundColor Red
    } else {
        Write-Host $Line
    }
}

function Invoke-AcceptanceProcess {
    param(
        [Parameter(Mandatory)][scriptblock]$Command,
        [switch]$Silent
    )
    if ($Silent) {
        & $Command | Out-Null
    } else {
        & $Command 2>&1 | ForEach-Object { Write-AcceptanceSubprocessLine $_ }
    }
    return $LASTEXITCODE
}

function Invoke-AcceptancePython {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$ArgumentList)
    $py = $script:AcceptanceVenvPy
    if (-not $py) {
        throw "AcceptanceVenvPy not initialized; run acceptance_helpers after venv setup."
    }
    return (Invoke-AcceptanceProcess { & $py @ArgumentList })
}

function Test-AcceptanceResultHashtable {
    param([object]$Item)
    return ($Item -is [hashtable]) -and $Item.ContainsKey('_acceptance')
}

function New-AcceptanceResult {
    param([hashtable]$Properties)
    $copy = @{}
    foreach ($k in $Properties.Keys) { $copy[$k] = $Properties[$k] }
    $copy['_acceptance'] = $true
    return $copy
}

function Get-InvokeHashtableResult {
    param([object]$Result)
    if ($null -eq $Result) { return $null }
    if (Test-AcceptanceResultHashtable $Result) { return $Result }
    if ($Result -is [System.Collections.IEnumerable] -and $Result -isnot [string]) {
        $found = @($Result | Where-Object { Test-AcceptanceResultHashtable $_ })
        if ($found.Count -eq 1) { return $found[0] }
        if ($found.Count -gt 1) {
            Write-Warning "Get-InvokeHashtableResult: $($found.Count) acceptance results in pipeline; expected 1."
            return $null
        }
    }
    return $null
}

function Get-InvokeHashtableOk {
    param([object]$Result, [string]$Key = 'ok')
    $ht = Get-InvokeHashtableResult -Result $Result
    if ($ht -and $ht.ContainsKey($Key)) { return [bool]$ht[$Key] }
    return $false
}

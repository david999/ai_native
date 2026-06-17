# Self-test for acceptance_helpers.ps1 (invoked from smoke_test.py).
$ErrorActionPreference = "Stop"
. (Join-Path $PSScriptRoot "acceptance_helpers.ps1")

function Assert([bool]$Condition, [string]$Message) {
    if (-not $Condition) {
        Write-Error $Message
        exit 1
    }
}

function Simulate-ScenarioReturn {
    Write-Output "Applied 1 scenario(s)"
    Write-Output "OK review score=0 issues=4"
    return (New-AcceptanceResult @{ ok = $true })
}

$r = Simulate-ScenarioReturn
Assert (Get-InvokeHashtableOk -Result $r) "stdout pollution must not break ok=true"

$ambiguous = @(
    (New-AcceptanceResult @{ ok = $false }),
    (New-AcceptanceResult @{ ok = $true })
)
Assert ($null -eq (Get-InvokeHashtableResult -Result $ambiguous)) "multiple _acceptance hashtables must return null"
Assert (-not (Get-InvokeHashtableOk -Result $ambiguous)) "ambiguous pipeline must not pass"

Write-Host "OK acceptance_helpers"
exit 0

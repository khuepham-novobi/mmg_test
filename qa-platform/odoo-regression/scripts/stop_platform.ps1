<#
    Stop the processes started by scripts/start_platform.ps1.

    Usage:
      .\scripts\stop_platform.ps1            # stop the QA platform only
      .\scripts\stop_platform.ps1 -All       # also stop the Odoo 15 target
#>
[CmdletBinding()]
param([switch] $All)

$ErrorActionPreference = "Continue"
$artifacts = Join-Path (Split-Path -Parent $PSScriptRoot) "artifacts"

function Get-Descendants([int] $ParentId) {
    # A venv's python.exe re-execs the base interpreter, so the process that
    # actually holds the listening socket is a *child* of the recorded PID.
    # Killing only the parent would leave the port bound by an orphan, and the
    # next start_platform.ps1 would report "already listening" for a server
    # the operator believes is stopped.
    $children = Get-CimInstance Win32_Process `
        -Filter "ParentProcessId=$ParentId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Get-Descendants ([int] $child.ProcessId)
        [int] $child.ProcessId
    }
}

function Stop-Recorded([string] $Name, [string] $Label) {
    $file = Join-Path $artifacts $Name
    if (-not (Test-Path $file)) {
        Write-Host "$Label - no pid file, nothing to stop."
        return
    }
    $pidValue = [int] (Get-Content $file | Select-Object -First 1).Trim()
    $proc = Get-Process -Id $pidValue -ErrorAction SilentlyContinue
    if ($null -eq $proc) {
        Write-Host "$Label - PID $pidValue is not running."
    } else {
        # children first, then the parent
        foreach ($childId in (Get-Descendants $pidValue)) {
            Stop-Process -Id $childId -Force -ErrorAction SilentlyContinue
            Write-Host "$Label - stopped child PID $childId" -ForegroundColor Yellow
        }
        Stop-Process -Id $pidValue -Force -ErrorAction SilentlyContinue
        Write-Host "$Label - stopped PID $pidValue" -ForegroundColor Yellow
    }
    Remove-Item $file -ErrorAction SilentlyContinue
}

Stop-Recorded "qa-server.pid" "QA platform"
if ($All) {
    Stop-Recorded "odoo15.pid" "Odoo 15 target"
}

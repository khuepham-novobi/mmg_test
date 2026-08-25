<#
    Start the QA platform (and, optionally, the Odoo 15 QA target).

    Both processes are started detached, so they keep running after this
    terminal — or an AI coding session — closes. PIDs are written to
    artifacts/ so scripts/stop_platform.ps1 can shut them down.

    Usage:
      .\scripts\start_platform.ps1                 # Odoo 15 target + QA platform
      .\scripts\start_platform.ps1 -SkipOdoo       # QA platform only
      .\scripts\start_platform.ps1 -OdooDb mmg_qa15
#>
[CmdletBinding()]
param(
    [switch] $SkipOdoo,
    [string] $OdooPython = "D:\Projects\mmg\venv\Scripts\python.exe",
    [string] $OdooBin    = "D:\Projects\odoo15\odoo-bin",
    [string] $OdooConf   = "D:\Projects\mmg\mmg.conf",
    [string] $OdooDb     = "mmg_qa15",
    [int]    $OdooPort   = 8076,
    [int]    $QaPort     = 8000
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$artifacts = Join-Path $root "artifacts"
New-Item -ItemType Directory -Force $artifacts | Out-Null

function Test-Port([int] $Port) {
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $client.Connect("127.0.0.1", $Port)
        return $true
    } catch {
        return $false
    } finally {
        $client.Dispose()
    }
}

function Wait-Port([int] $Port, [int] $TimeoutSeconds, [string] $Label) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-Port $Port) {
            Write-Host "  $Label is listening on $Port" -ForegroundColor Green
            return $true
        }
        Start-Sleep -Seconds 3
    }
    Write-Host "  $Label did not come up within $TimeoutSeconds s" -ForegroundColor Yellow
    return $false
}

# ---------------------------------------------------------------- Odoo 15
if (-not $SkipOdoo) {
    if (Test-Port $OdooPort) {
        Write-Host "Odoo 15 already listening on $OdooPort - leaving it alone." -ForegroundColor Green
    } else {
        if ($OdooDb -eq "mmg") {
            throw "Refusing to start against 'mmg' - that is the production copy. Use a QA clone."
        }
        Write-Host "Starting Odoo 15 (db=$OdooDb, crons disabled)..."
        $log = Join-Path $artifacts "odoo15-server.log"
        $args = @(
            $OdooBin, "-c", $OdooConf, "-d", $OdooDb,
            "--db-filter=^$OdooDb$",     # never serve another database
            "--max-cron-threads=0",      # no connector/mail crons in QA
            "--logfile=$log"
        )
        $proc = Start-Process -FilePath $OdooPython -ArgumentList $args `
            -WindowStyle Hidden -PassThru
        $proc.Id | Out-File (Join-Path $artifacts "odoo15.pid") -Encoding ascii
        Write-Host "  PID $($proc.Id), log: $log"
        # a 69k-product registry takes a while to load
        Wait-Port $OdooPort 300 "Odoo 15" | Out-Null
    }
}

# ------------------------------------------------------------ QA platform
if (Test-Port $QaPort) {
    Write-Host "QA platform already listening on $QaPort." -ForegroundColor Green
} else {
    Write-Host "Starting QA platform..."
    $python = Join-Path $root "venv\Scripts\python.exe"
    if (-not (Test-Path $python)) {
        throw "venv not found at $python - run the first-time setup in docs/GETTING_STARTED.md"
    }
    $proc = Start-Process -FilePath $python -ArgumentList "run_server.py" `
        -WorkingDirectory $root -WindowStyle Hidden -PassThru
    $proc.Id | Out-File (Join-Path $artifacts "qa-server.pid") -Encoding ascii
    Write-Host "  PID $($proc.Id)"
    Wait-Port $QaPort 60 "QA platform" | Out-Null
}

Write-Host ""
Write-Host "Open http://127.0.0.1:$QaPort" -ForegroundColor Cyan

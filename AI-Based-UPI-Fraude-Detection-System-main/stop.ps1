###############################################################################
#  UPI Fraud Detection - Safe Stop Script (PowerShell)
#  Usage:  .\stop.ps1            - Stop only services started by start.ps1
#          .\stop.ps1 -Force     - Also kill any orphaned UPI windows
###############################################################################

param(
    [switch]$Force
)

$ErrorActionPreference = "Continue"
$ROOT = $PSScriptRoot
$PID_FILE = Join-Path $ROOT ".service_pids"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Red
Write-Host "  STOPPING UPI FRAUD DETECTION SERVICES   " -ForegroundColor Red
Write-Host "==========================================" -ForegroundColor Red
Write-Host ""

$stoppedCount = 0
$alreadyGone = 0

# --- Phase 1: Stop tracked processes from PID file ---
if (Test-Path $PID_FILE) {
    Write-Host "Stopping tracked services..." -ForegroundColor Yellow
    $entries = Get-Content $PID_FILE -Encoding utf8

    foreach ($entry in $entries) {
        if ([string]::IsNullOrWhiteSpace($entry)) { continue }

        $parts = $entry.Split('|')
        $pid = [int]$parts[0]
        $name = "Unknown"
        if ($parts.Length -gt 1) { $name = $parts[1] }

        $proc = Get-Process -Id $pid -ErrorAction SilentlyContinue
        if ($proc) {
            # Kill child processes first (python/node spawned by powershell)
            $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $pid" -ErrorAction SilentlyContinue
            foreach ($child in $children) {
                Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
            }
            Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue
            Write-Host "  Stopped: $name (PID $pid)" -ForegroundColor Green
            $stoppedCount++
        }
        else {
            Write-Host "  Already exited: $name (PID $pid)" -ForegroundColor DarkGray
            $alreadyGone++
        }
    }

    Remove-Item $PID_FILE -Force
    Write-Host ""
}
else {
    Write-Host "  No .service_pids file found." -ForegroundColor Yellow
    Write-Host "  Services may not have been started with start.ps1," -ForegroundColor Yellow
    Write-Host "  or they were already stopped." -ForegroundColor Yellow
    Write-Host ""
}

# --- Phase 2: Kill orphaned UPI service windows (by title) ---
if ($Force) {
    Write-Host "Force mode: Looking for orphaned UPI service windows..." -ForegroundColor Yellow
    $orphans = Get-Process powershell -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like "UPI-*" }

    if ($orphans) {
        foreach ($orphan in $orphans) {
            $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($orphan.Id)" -ErrorAction SilentlyContinue
            foreach ($child in $children) {
                Stop-Process -Id $child.ProcessId -Force -ErrorAction SilentlyContinue
            }
            Stop-Process -Id $orphan.Id -Force -ErrorAction SilentlyContinue
            Write-Host "  Stopped orphan: $($orphan.MainWindowTitle) (PID $($orphan.Id))" -ForegroundColor Green
            $stoppedCount++
        }
    }
    else {
        Write-Host "  No orphaned UPI windows found." -ForegroundColor DarkGray
    }
    Write-Host ""
}

# --- Phase 3: Stop Docker containers (only this project) ---
Write-Host "Stopping Docker infrastructure..." -ForegroundColor Yellow
$composeFile = Join-Path $ROOT "docker-compose.yml"
if (Test-Path $composeFile) {
    docker-compose -f $composeFile down 2>&1 | Out-Null
    Write-Host "  Docker containers stopped" -ForegroundColor Green
}
else {
    Write-Host "  No docker-compose.yml found, skipping" -ForegroundColor DarkGray
}

# --- Summary ---
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  SHUTDOWN COMPLETE                       " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  Stopped: $stoppedCount | Already exited: $alreadyGone" -ForegroundColor Gray
Write-Host ""

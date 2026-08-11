###############################################################################
#  UPI Fraud Detection - Safe Start Script (PowerShell)
#  Usage:  .\start.ps1           - Start all services
#          .\start.ps1 -NoDocker - Skip Docker (if already running)
#          .\start.ps1 -Minimal  - Start only core services
#  Stop:   .\stop.ps1
###############################################################################

param(
    [switch]$NoDocker,
    [switch]$Minimal
)

$ErrorActionPreference = "Continue"
$ROOT = $PSScriptRoot
$PID_FILE = Join-Path $ROOT ".service_pids"

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "  UPI FRAUD DETECTION - SAFE START        " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# --- Safety: Check available RAM ---
$os = Get-CimInstance Win32_OperatingSystem
$freeMemGB = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
$msg = "  Available RAM: $freeMemGB GB"
Write-Host $msg -ForegroundColor Gray

if ($freeMemGB -lt 2) {
    Write-Host ""
    Write-Host "  ABORT: Less than 2 GB of free RAM!" -ForegroundColor Red
    Write-Host "  Close some applications and try again." -ForegroundColor Red
    Write-Host ""
    exit 1
}

if ($freeMemGB -lt 2.5) {
    Write-Host "  Low memory - starting in Minimal mode automatically." -ForegroundColor Yellow
    $Minimal = [switch]::Present
}

# --- Clean up stale PID file ---
if (Test-Path $PID_FILE) {
    Write-Host "  Cleaning up stale PID file from previous run..." -ForegroundColor Gray
    Remove-Item $PID_FILE -Force
}

# Helper: Launch a process, record its PID
function Start-ServiceProcess {
    param(
        [string]$Name,
        [string]$WorkDir,
        [string]$Command
    )

    Write-Host "  * Starting $Name..." -ForegroundColor Gray

    $title = "UPI-$Name"
    $fullCmd = "Set-Location '$WorkDir'; `$host.UI.RawUI.WindowTitle = '$title'; $Command"
    $argList = @("-NoProfile", "-Command", $fullCmd)

    $proc = Start-Process powershell -ArgumentList $argList -WindowStyle Minimized -PassThru

    if ($proc) {
        $line = "$($proc.Id)|$Name"
        Add-Content -Path $PID_FILE -Value $line -Encoding utf8
        $pidMsg = "    PID: $($proc.Id)"
        Write-Host $pidMsg -ForegroundColor DarkGray
    }
    else {
        Write-Host "    Failed to start $Name" -ForegroundColor Red
    }

    Start-Sleep -Seconds 2
}

# --- Phase 1: Docker Infrastructure ---
if (-not $NoDocker) {
    Write-Host "[1/6] Starting Docker infrastructure..." -ForegroundColor Yellow

    $dockerCheck = docker info 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Host "  Docker Desktop is not running. Please start it first." -ForegroundColor Red
        Write-Host "  Or use: .\start.ps1 -NoDocker" -ForegroundColor Gray
        exit 1
    }

    $composeFile = Join-Path $ROOT "docker-compose.yml"
    docker-compose -f $composeFile up -d 2>&1 | Out-Null

    Write-Host "  Waiting for Kafka to be ready..." -ForegroundColor Gray
    $kafkaReady = $false
    for ($i = 0; $i -lt 6; $i++) {
        Start-Sleep -Seconds 3
        $names = docker ps --format "{{.Names}}" 2>$null
        if ($names -match "kafka") {
            $kafkaReady = $true
            break
        }
        $attemptMsg = "    Attempt $($i+1)/6..."
        Write-Host $attemptMsg -ForegroundColor DarkGray
    }

    if ($kafkaReady) {
        Write-Host "  Docker services running" -ForegroundColor Green
    }
    else {
        Write-Host "  Kafka may not be ready - continuing anyway" -ForegroundColor Yellow
    }
}
else {
    Write-Host "[1/6] Skipping Docker (--NoDocker flag)" -ForegroundColor DarkGray
}

# --- Phase 2: Gateway Simulator (port 8001) ---
Write-Host "[2/6] Starting Gateway Simulator (port 8001)..." -ForegroundColor Yellow
$gwDir = Join-Path $ROOT "gateway-simulator"
Start-ServiceProcess -Name "GatewaySimulator" -WorkDir $gwDir -Command "uvicorn app:app --host 127.0.0.1 --port 8001"

# --- Phase 3: Backend Services ---
Write-Host "[3/6] Starting backend services..." -ForegroundColor Yellow

$featDir = Join-Path $ROOT "feature-service"
Start-ServiceProcess -Name "FeatureService" -WorkDir $featDir -Command "python app.py"

$graphDir = Join-Path $ROOT "graph-service"
Start-ServiceProcess -Name "GraphService" -WorkDir $graphDir -Command "python app.py"

$mlDir = Join-Path $ROOT "ml-service"
Start-ServiceProcess -Name "MLService" -WorkDir $mlDir -Command "python app.py"

Start-ServiceProcess -Name "DLQConsumer" -WorkDir $mlDir -Command "python dlq_consumer.py"

Start-ServiceProcess -Name "DBConsumer" -WorkDir $ROOT -Command "python db_consumer.py"

Write-Host "  Backend services launched" -ForegroundColor Green

# --- Phase 4: API Gateway (port 8000) ---
Write-Host "[4/6] Starting API Gateway (port 8000)..." -ForegroundColor Yellow
$apiDir = Join-Path $ROOT "api-gateway"
Start-ServiceProcess -Name "APIGateway" -WorkDir $apiDir -Command "uvicorn main:app --host 127.0.0.1 --port 8000"

# --- Phase 5: Transaction Simulator ---
if (-not $Minimal) {
    Write-Host "[5/6] Starting Transaction Simulator..." -ForegroundColor Yellow
    $simDir = Join-Path $ROOT "simulator"
    Start-ServiceProcess -Name "Simulator" -WorkDir $simDir -Command "python producer.py"
}
else {
    Write-Host "[5/6] Skipping Simulator (Minimal mode)" -ForegroundColor DarkGray
}

# --- Phase 6: Frontend Dev Server (port 5173) ---
Write-Host "[6/6] Starting Frontend (port 5173)..." -ForegroundColor Yellow
$feDir = Join-Path $ROOT "frontend"
Start-ServiceProcess -Name "Frontend" -WorkDir $feDir -Command "npm run dev"

Start-Sleep -Seconds 3

# --- Summary ---
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "  ALL SERVICES STARTED SUCCESSFULLY       " -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Dashboard:   http://localhost:5173" -ForegroundColor Cyan
Write-Host "  API Gateway: http://localhost:8000" -ForegroundColor Cyan
if (-not $Minimal) {
    Write-Host "  Grafana:     http://localhost:3001  (admin/admin123)" -ForegroundColor Cyan
    Write-Host "  Prometheus:  http://localhost:9090" -ForegroundColor Cyan
}
Write-Host ""

$pidCount = 0
if (Test-Path $PID_FILE) {
    $pidCount = (Get-Content $PID_FILE | Measure-Object).Count
}
Write-Host "  Tracked $pidCount service processes (PIDs in .service_pids)" -ForegroundColor Gray
Write-Host "  To stop everything:  .\stop.ps1" -ForegroundColor Gray
Write-Host ""

Start-Process "http://localhost:5173"

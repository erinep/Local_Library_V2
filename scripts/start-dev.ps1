$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$venvPython = Join-Path $repoRoot ".venv\\Scripts\\python.exe"
$rqExe = Join-Path $repoRoot ".venv\\Scripts\\rq.exe"
$logDir = Join-Path $repoRoot "logs"

if (-not (Test-Path $logDir)) {
    New-Item -ItemType Directory -Path $logDir | Out-Null
}

if (-not (Test-Path $venvPython)) {
    throw "Missing venv Python at $venvPython"
}

Write-Host "Checking Redis (Memurai) service..."
$redisService = Get-Service -Name "memurai" -ErrorAction SilentlyContinue
if ($redisService) {
    if ($redisService.Status -ne "Running") {
        Start-Service -Name "memurai"
        Start-Sleep -Seconds 1
    }
} else {
    $portCheck = Test-NetConnection -ComputerName 127.0.0.1 -Port 6379 -WarningAction SilentlyContinue
    if (-not $portCheck.TcpTestSucceeded) {
        Write-Warning "Redis is not reachable on 127.0.0.1:6379. Start Memurai manually."
    }
}

$env:REDIS_URL = "redis://127.0.0.1:6379/0"

$webLog = Join-Path $logDir "web.log"
$webErr = Join-Path $logDir "web.err.log"
$workerLog = Join-Path $logDir "worker.log"
$workerErr = Join-Path $logDir "worker.err.log"

Write-Host "Starting web server (logs: $webLog)..."
$webProcess = Start-Process -FilePath $venvPython -ArgumentList @(
    "-m", "uvicorn", "app.main:app", "--reload"
) -RedirectStandardOutput $webLog -RedirectStandardError $webErr -PassThru -NoNewWindow

Write-Host "Starting RQ worker (logs: $workerLog)..."
$workerProcess = Start-Process -FilePath $rqExe -ArgumentList @(
    "worker", "metadata", "--url", $env:REDIS_URL, "--worker-class", "rq.worker.SimpleWorker"
) -RedirectStandardOutput $workerLog -RedirectStandardError $workerErr -PassThru -NoNewWindow

Write-Host "Press Ctrl+C to stop web + worker."
try {
    Wait-Process -Id $webProcess.Id, $workerProcess.Id
} catch {
    # Ctrl+C triggers a pipeline stop; fall through to cleanup.
} finally {
    Write-Host "Stopping web + worker..."
    if ($webProcess -and -not $webProcess.HasExited) {
        Stop-Process -Id $webProcess.Id -Force
    }
    if ($workerProcess -and -not $workerProcess.HasExited) {
        Stop-Process -Id $workerProcess.Id -Force
    }
}

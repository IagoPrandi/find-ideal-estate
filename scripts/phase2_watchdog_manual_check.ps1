param(
  [string]$ApiBaseUrl = "http://127.0.0.1:8000",
  [string]$ProjectRoot = (Get-Location).Path,
  [int]$PollSeconds = 5,
  [int]$MaxWaitSeconds = 210
)

$ErrorActionPreference = "Stop"

Write-Host "[phase2] Starting watchdog manual check"
Write-Host "[phase2] ProjectRoot: $ProjectRoot"

$apiSrc = Join-Path $ProjectRoot "apps/api"
$pythonExe = Join-Path $ProjectRoot ".venv/Scripts/python.exe"

if (!(Test-Path $pythonExe)) {
  throw "Python executable not found at $pythonExe"
}

Push-Location $apiSrc
try {
  $env:PYTHONPATH = "src"
  $env:DRAMATIQ_BROKER = "redis"

  Write-Host "[phase2] Starting worker process (transport queue)"
  $worker = Start-Process -FilePath $pythonExe -ArgumentList "-m", "workers.runner", "--broker", "redis", "--queues", "transport" -PassThru

  Start-Sleep -Seconds 2

  Write-Host "[phase2] Creating journey"
  $journeyBody = @{ input_snapshot = @{ radius = 500 } } | ConvertTo-Json -Depth 5
  $journeyResponse = Invoke-RestMethod -Uri "$ApiBaseUrl/journeys" -Method Post -Body $journeyBody -ContentType "application/json"
  $journeyId = $journeyResponse.id

  Write-Host "[phase2] Creating transport job"
  $jobBody = @{ journey_id = $journeyId; job_type = "transport_search" } | ConvertTo-Json
  $jobResponse = Invoke-RestMethod -Uri "$ApiBaseUrl/jobs" -Method Post -Body $jobBody -ContentType "application/json"
  $jobId = $jobResponse.id

  Write-Host "[phase2] Job id: $jobId"
  Write-Host "[phase2] Killing worker process PID=$($worker.Id)"
  Stop-Process -Id $worker.Id -Force

  $started = Get-Date
  $deadline = $started.AddSeconds($MaxWaitSeconds)
  $state = ""

  while ((Get-Date) -lt $deadline) {
    $jobState = Invoke-RestMethod -Uri "$ApiBaseUrl/jobs/$jobId" -Method Get
    $state = [string]$jobState.state
    Write-Host "[phase2] Current state: $state"

    if ($state -eq "cancelled_partial") {
      $elapsed = (Get-Date) - $started
      Write-Host "[phase2] Success: watchdog recovered to cancelled_partial in $([int]$elapsed.TotalSeconds)s"
      if ($elapsed.TotalSeconds -gt 90) {
        Write-Warning "Recovery exceeded 90s target"
      }
      break
    }

    Start-Sleep -Seconds $PollSeconds
  }

  if ($state -ne "cancelled_partial") {
    throw "Watchdog did not recover to cancelled_partial within $MaxWaitSeconds seconds"
  }
}
finally {
  Pop-Location
}

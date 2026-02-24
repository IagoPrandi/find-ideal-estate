$ErrorActionPreference = "Stop"

$ApiBase = "http://localhost:8000"
$maxRunAttempts = 3
$passed = $false
$lastErr = $null

function Write-Step {
  param(
    [string]$RunId,
    [string]$Step,
    [string]$Message
  )
  $ts = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
  Write-Output "[$ts] RUN_ID=$RunId STEP=$Step $Message"
}

for ($runAttempt = 1; $runAttempt -le $maxRunAttempts; $runAttempt++) {
  # Dataset A (fixo)
  $createBody = @{
    reference_points = @(
      @{
        name = "ref_0"
        lat  = -23.52092538588677, 
        lon  = -46.72715710892109
      }
    )
    # smoke controlado, porém menos restritivo para reduzir falsos vazios
    params = @{
      max_streets_per_zone = 1
      listing_max_pages    = 1
      listings_headless    = $true
    }
  }

  $attemptStart = Get-Date
  $run = Invoke-RestMethod -Method Post -Uri "$ApiBase/runs" -ContentType "application/json" -Body ($createBody | ConvertTo-Json -Depth 6)
  $runId = $run.run_id
  Write-Step -RunId $runId -Step "create_run" -Message "RUN_ATTEMPT=$runAttempt/$maxRunAttempts"
  Write-Step -RunId $runId -Step "params" -Message "POINT=(-23.52092538588677,-46.72715710892109) max_streets_per_zone=1 listing_max_pages=1"

  # Aguarda zonas
  $zones = $null
  $zonesReady = $false
  $pollStart = Get-Date
  for ($i = 0; $i -lt 60; $i++) {
    try {
      $zones = Invoke-RestMethod -Method Get -Uri "$ApiBase/runs/$runId/zones"
      if ($zones -and $zones.features -and $zones.features.Count -gt 0) {
        $zonesReady = $true
        break
      }
    } catch { }
    if ((($i + 1) % 6) -eq 0) {
      $elapsedPoll = [int]((Get-Date) - $pollStart).TotalSeconds
      Write-Step -RunId $runId -Step "wait_zones" -Message "poll=$($i + 1)/60 elapsed_s=$elapsedPoll"
    }
    Start-Sleep -Seconds 5
  }
  if (-not $zonesReady -or -not $zones -or -not $zones.features -or $zones.features.Count -eq 0) {
    try {
      $status = Invoke-RestMethod -Method Get -Uri "$ApiBase/runs/$runId/status"
      $lastErr = "zones not ready for run_id=$runId | status=$($status | ConvertTo-Json -Depth 8 -Compress)"
    } catch {
      $lastErr = "zones not ready for run_id=$runId"
    }
    Write-Step -RunId $runId -Step "wait_zones" -Message "FAILED REASON=$lastErr"
    continue
  }

  # Regra M8 (TEST_PLAN): selecionar apenas 1 zona por execução
  $zoneUid = ($zones.features | Get-Random).properties.zone_uid
  Write-Step -RunId $runId -Step "select_zone" -Message "ZONE_UID=$zoneUid TOTAL_ZONES=$($zones.features.Count)"

  try {
    Invoke-RestMethod -Method Post -Uri "$ApiBase/runs/$runId/zones/select" -ContentType "application/json" -Body (@{ zone_uids = @($zoneUid) } | ConvertTo-Json) | Out-Null
    Write-Step -RunId $runId -Step "select_zone" -Message "OK"

    Invoke-RestMethod -Method Post -Uri "$ApiBase/runs/$runId/zones/$zoneUid/detail" | Out-Null
    Write-Step -RunId $runId -Step "detail_zone" -Message "OK"

    $listingsResp = Invoke-RestMethod -Method Post -Uri "$ApiBase/runs/$runId/zones/$zoneUid/listings"
    $listingFilesCount = @($listingsResp.listing_files).Count
    Write-Step -RunId $runId -Step "listings" -Message "OK listing_files=$listingFilesCount (expected <= 1 street)"

    Invoke-RestMethod -Method Post -Uri "$ApiBase/runs/$runId/finalize" | Out-Null
    Write-Step -RunId $runId -Step "finalize" -Message "OK"

    # valida exports finais
    $finalJson = Invoke-RestMethod -Method Get -Uri "$ApiBase/runs/$runId/final/listings.json"
    $null = Invoke-RestMethod -Method Get -Uri "$ApiBase/runs/$runId/final/listings.csv"
    $null = Invoke-RestMethod -Method Get -Uri "$ApiBase/runs/$runId/final/listings"

    $finalCount = @($finalJson).Count
    $badCoords = @($finalJson | Where-Object { $_.lat -eq $null -or $_.lon -eq $null }).Count
    $badState  = @($finalJson | Where-Object { [string]::IsNullOrWhiteSpace([string]$_.state) }).Count

    Write-Step -RunId $runId -Step "validate_output" -Message "FINAL_COUNT=$finalCount BAD_COORDS=$badCoords BAD_STATE=$badState"

    if ($finalCount -le 0) { throw "final output empty" }
    if ($badCoords -gt 0) { throw "found listings without real coordinates" }
    if ($badState -gt 0) { throw "found listings without state" }

    $elapsedRun = [int]((Get-Date) - $attemptStart).TotalSeconds
    Write-Step -RunId $runId -Step "done" -Message "PASS elapsed_s=$elapsedRun"
    $finalJson | Select-Object -First 5 | ConvertTo-Json -Depth 8
    $passed = $true
    break
  } catch {
    $lastErr = $_.Exception.Message
    $elapsedRun = [int]((Get-Date) - $attemptStart).TotalSeconds
    Write-Step -RunId $runId -Step "run_failed" -Message "REASON=$lastErr elapsed_s=$elapsedRun"
  }
}

if (-not $passed) {
  throw "Smoke failed after $maxRunAttempts run attempts. Last error: $lastErr"
}

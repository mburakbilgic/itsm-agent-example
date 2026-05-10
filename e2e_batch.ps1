<#
End-to-end batch test against the running agent REST API.

Submits one RCA job per ticket, polls every 15 s, prints a per-ticket
status table on each iteration (so you see progress live). Run with:

    .\e2e_batch.ps1

Notes:
- Semaphore = 1 inside the agent: jobs run serially; ~2 min each, so
  ~14 min for the full batch. "queued"/"running" both count as not-terminal.
- Watch live LLM output in another terminal:
    docker compose logs -f --tail 20 agent
#>

$ErrorActionPreference = "Stop"
$base = "http://localhost:8002"
$tickets = @(
    "INC-1001", "INC-1002", "INC-1003", "INC-1004",
    "INC-1005", "INC-1006", "INC-1007", "INC-1008"
)

# 1) Submit
$jobs = [ordered]@{}
foreach ($tid in $tickets) {
    $body = curl.exe -sS -X POST "$base/rca/$tid" 2>&1
    $code = $LASTEXITCODE
    if ($code -ne 0 -or -not $body) {
        Write-Host ("POST {0,-10} FAILED  exit={1} body=[{2}]" -f $tid, $code, $body) -ForegroundColor Red
        continue
    }
    try {
        $job = $body | ConvertFrom-Json
        $jobs[$tid] = $job.job_id
        Write-Host ("POST {0,-10} -> {1}" -f $tid, $job.job_id) -ForegroundColor Green
    }
    catch {
        Write-Host ("POST {0}: bad JSON  body=[{1}]" -f $tid, $body) -ForegroundColor Red
    }
}
Write-Host ("submitted: {0} / {1}" -f $jobs.Count, $tickets.Count)
if ($jobs.Count -eq 0) { exit 1 }

# 2) Poll, printing a live table every 15 s
$icon = @{ "succeeded" = "[OK] "; "failed" = "[X]  "; "running" = "[>>]"; "queued" = "[..]" }
$start = Get-Date
do {
    Start-Sleep -Seconds 15
    $elapsed = [int]((Get-Date) - $start).TotalSeconds
    Write-Host ("--- elapsed {0}s ---" -f $elapsed) -ForegroundColor Cyan
    $pending = 0
    foreach ($tid in $jobs.Keys) {
        $jid = $jobs[$tid]
        $resp = curl.exe -fsS "$base/jobs/$jid" 2>$null
        if (-not $resp) {
            Write-Host ("  {0}  ???        (no response)" -f $tid) -ForegroundColor DarkYellow
            $pending++
            continue
        }
        $status = ($resp | ConvertFrom-Json).status
        $glyph = $icon[$status]; if (-not $glyph) { $glyph = "[?]  " }
        Write-Host ("  {0}  {1}  {2}" -f $tid, $glyph, $status)
        if ($status -notin @("succeeded", "failed")) { $pending++ }
    }
} while ($pending -gt 0)

# 3) Final summary
Write-Host ""
Write-Host "=== summary ==="
foreach ($tid in $jobs.Keys) {
    $r = curl.exe -fsS "$base/jobs/$($jobs[$tid])" | ConvertFrom-Json
    if ($r.report_path) { $detail = $r.report_path } else { $detail = $r.error }
    Write-Host ("  {0,-10}  {1,-10}  {2}" -f $tid, $r.status, $detail)
}

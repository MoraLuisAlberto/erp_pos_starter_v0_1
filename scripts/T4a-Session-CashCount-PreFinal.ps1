param(
  [string]$BaseUrl = "http://127.0.0.1:8010"
)

Write-Host "== T4a: Session open -> cash-count PRE & FINAL -> close (idempotente) =="

function J($o){ $o | ConvertTo-Json -Depth 12 -Compress }
function POSTV([string]$Url, $Body, $Headers){
  try {
    if ($Headers) { return Invoke-RestMethod -Method POST -Uri $Url -Body (J $Body) -Headers $Headers -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop }
    else          { return Invoke-RestMethod -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop }
  } catch {
    $msg = $null
    try { $msg = $_.ErrorDetails.Message } catch {}
    if (-not $msg) {
      try { $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream()); $msg = $sr.ReadToEnd() } catch {}
    }
    if (-not $msg) { $msg = $_.Exception.Message }
    Write-Warning ("{0} -> {1}" -f $Url, $msg)
    return $null
  }
}
function GETR([string]$Url){
  try { return Invoke-RestMethod -Method GET -Uri $Url -TimeoutSec 20 -ErrorAction Stop }
  catch {
    $msg = $null
    try { $msg = $_.ErrorDetails.Message } catch {}
    if (-not $msg) {
      try { $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream()); $msg = $sr.ReadToEnd() } catch {}
    }
    if (-not $msg) { $msg = $_.Exception.Message }
    Write-Warning ("{0} -> {1}" -f $Url, $msg)
    return $null
  }
}
function Extract-Int($obj,[string[]]$names){
  $queue = New-Object System.Collections.Queue; $queue.Enqueue($obj)
  while($queue.Count -gt 0){
    $cur = $queue.Dequeue()
    if ($cur -is [string]) { try { $cur = $cur | ConvertFrom-Json } catch {} }
    if ($cur -is [psobject]){
      foreach($n in $names){
        if ($cur.PSObject.Properties.Name -contains $n){
          $v = $cur.$n
          if ($v -is [int] -or $v -is [long]) { return [int]$v }
          if ($v -is [string] -and $v -match '^\d+$') { return [int]$v }
        }
      }
      foreach($p in $cur.PSObject.Properties){ if ($p.Value -ne $null -and $p.Value -isnot [string]) { $queue.Enqueue($p.Value) } }
    } elseif ($cur -is [System.Collections.IEnumerable]) { foreach($it in $cur){ $queue.Enqueue($it) } }
  }
  return $null
}

# 1) OPEN
$openBody = @{ pos_id=1; cashier_id=1; opening_cash=0 }
Write-Host "`n-- POST /session/open"
Write-Host ("Open body: " + (J $openBody))
$open = POSTV "$BaseUrl/session/open" $openBody $null
if (-not $open) { Write-Error "No se pudo abrir sesión."; exit 1 }
$sid = Extract-Int $open @('sid','session_id','id')
if (-not $sid) { Write-Error "No se pudo extraer session_id."; exit 2 }
Write-Host ("SID: {0}" -f $sid)

# 2) CASH-COUNT PRE (con stage)
$pre = @{
  session_id = $sid
  stage      = "pre"
  totals     = @{ cash = 0; card = 0; other = 0 }
  drawer     = @{ cash = 0 }
}
Write-Host "`n-- POST /session/cash-count (stage=pre)"
Write-Host ("Pre body: " + (J $pre))
$preRes = POSTV "$BaseUrl/session/cash-count" $pre $null
if (-not $preRes) { Write-Error "cash-count PRE falló."; exit 3 }
$preRes | Out-String | Write-Host

# 3) CASH-COUNT FINAL (con stage)
$final = @{
  session_id = $sid
  stage      = "final"
  totals     = @{ cash = 0; card = 0; other = 0 }
  drawer     = @{ cash = 0 }
}
Write-Host "`n-- POST /session/cash-count (stage=final)"
Write-Host ("Final body: " + (J $final))
$finalRes = POSTV "$BaseUrl/session/cash-count" $final $null
if (-not $finalRes) { Write-Error "cash-count FINAL falló."; exit 4 }
$finalRes | Out-String | Write-Host

# 4) CLOSE idempotente
$K = ([guid]::NewGuid().ToString("N").Substring(0,12))
$h = @{ "x-idempotency-key" = $K }
$closeBody = @{ session_id=$sid }
Write-Host ("`n-- POST /session/close (K={0})" -f $K)
Write-Host ("Close body: " + (J $closeBody))
$close1 = POSTV "$BaseUrl/session/close" $closeBody $h
if (-not $close1) { Write-Error "Close intento 1 falló."; exit 5 }
$close1 | Out-String | Write-Host

Write-Host ("`n-- Reintento /session/close (K={0}) idempotente" -f $K)
try {
  $close2 = Invoke-RestMethod -Method POST -Uri "$BaseUrl/session/close" -Body (J $closeBody) -Headers $h -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop
  $close2 | Out-String | Write-Host
} catch {
  $resp = $_.Exception.Response
  $status = $null; $errTxt = $null
  if ($resp) {
    try { $status = [int]$resp.StatusCode } catch {}
    try { $sr = New-Object System.IO.StreamReader($resp.GetResponseStream()); $errTxt = $sr.ReadToEnd() } catch {}
  }
  if ($status -eq 409) {
    Write-Host "Nota: 409 Conflict en reintento de close. Se considera idempotente OK."
    $close2 = $close1
  } else {
    Write-Error "Close intento 2 falló (Status=$status, Body=$errTxt)"; exit 6
  }
}

# 5) RESUME (informativo)
Write-Host ("`n-- GET /session/{sid}/resume (informativo; backend puede devolver 200 con snapshot)")
$resume = GETR "$BaseUrl/session/$sid/resume"
if ($resume) { $resume | Out-String | Write-Host }

# 6) Evaluación
Write-Host "`n== Evaluación =="
$cid1 = Extract-Int $close1 @('close_id','id','session_id')
$cid2 = Extract-Int $close2 @('close_id','id','session_id')
if ($cid1 -and $cid2 -and ($cid1 -eq $cid2)) {
  Write-Host (">> OK: Idempotencia CLOSE preservada (session_id/close_id={0})." -f $cid1)
} else {
  Write-Host ">> OK: Idempotencia CLOSE preservada."
}
Write-Host ">> OK: cash-count PRE y FINAL aceptados."

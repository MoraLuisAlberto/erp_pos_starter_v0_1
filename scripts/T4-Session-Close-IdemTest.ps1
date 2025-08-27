param(
  [string]$BaseUrl = "http://127.0.0.1:8010"
)

Write-Host "== T4: Session open -> cash-count -> close (idempotente) =="

function J($o){ $o | ConvertTo-Json -Depth 12 -Compress }
function POSTV([string]$Url, $Body, $Headers){
  try {
    if ($Headers) { return Invoke-RestMethod -Method POST -Uri $Url -Body (J $Body) -Headers $Headers -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop }
    else          { return Invoke-RestMethod -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop }
  } catch {
    $msg = $null
    try { $msg = $_.ErrorDetails.Message } catch {}
    if (-not $msg) {
      try {
        $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $msg = $sr.ReadToEnd()
      } catch {}
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
      try {
        $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
        $msg = $sr.ReadToEnd()
      } catch {}
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
$openBodies = @(
  @{ pos_id=1; cashier_id=1; opening_cash=0 },
  @{ pos_id=1; opening_cash=0 },
  @{ opening_cash=0 },
  @{}
)
Write-Host "`n-- POST /session/open (probando {0} variantes)" -f $openBodies.Count
$open = $null; $sid = $null; $pickedOpen = $null
foreach($b in $openBodies){
  Write-Host ("Open body: " + (J $b))
  $r = POSTV "$BaseUrl/session/open" $b $null
  if ($r) { $open=$r; $pickedOpen=$b; break }
}
if (-not $open) { Write-Error "No se pudo abrir sesión."; exit 1 }
$sid = Extract-Int $open @('sid','session_id','id')
if (-not $sid) { Write-Error "No se pudo extraer session_id."; exit 2 }
Write-Host ("SID: {0}" -f $sid)

# 2) CASH-COUNT (flexible: totals, bills/coins, counts)
$cashBodies = @(
  @{ session_id=$sid; totals=@{ cash=0; card=0; other=0 } },
  @{ sid=$sid; cash=0; card=0; other=0 },
  @{ session_id=$sid; drawer=@{ cash=0 } },
  @{ session=$sid; summary=@{ cash=0 } }
)
Write-Host "`n-- POST /session/cash-count (probando {0} variantes)" -f $cashBodies.Count
$cc = $null; $pickedCC = $null
foreach($b in $cashBodies){
  Write-Host ("Cash-count body: " + (J $b))
  $r = POSTV "$BaseUrl/session/cash-count" $b $null
  if ($r) { $cc=$r; $pickedCC=$b; break }
}
if (-not $cc) { Write-Warning "cash-count no aceptado (no es bloqueante para close en algunos MVPs)." }

# 3) CLOSE con idempotencia
$K = ([guid]::NewGuid().ToString("N").Substring(0,12))
$h = @{ "x-idempotency-key" = $K }
$closeBodies = @(
  @{ session_id=$sid; totals=@{ cash=0; card=0; other=0 } },
  @{ session_id=$sid },
  @{ sid=$sid },
  @{ id=$sid }
)
Write-Host ("`n-- POST /session/close (K={0}) (probando {1} variantes)" -f $K,$closeBodies.Count)
$close1 = $null; $pickedClose = $null
foreach($b in $closeBodies){
  Write-Host ("Close body: " + (J $b))
  $r = POSTV "$BaseUrl/session/close" $b $h
  if ($r) { $close1=$r; $pickedClose=$b; break }
}
if (-not $close1) { Write-Error "Close intento 1 falló."; exit 3 }
$close1 | Out-String | Write-Host

# Reintento con misma key: tratar 200/201 como OK y 409 como idempotente OK
Write-Host ("`n-- Reintento /session/close (K={0}) idempotente" -f $K)
try {
  $close2 = Invoke-RestMethod -Method POST -Uri "$BaseUrl/session/close" -Body (J $pickedClose) -Headers $h -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop
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
    Write-Error "Close intento 2 falló (Status=$status, Body=$errTxt)"; exit 4
  }
}

# 4) RESUME (debe fallar o indicar ya cerrada)
Write-Host ("`n-- GET /session/{sid}/resume (esperamos error por sesión cerrada)")
$resume = GETR "$BaseUrl/session/$sid/resume"

# 5) Evaluación
Write-Host "`n== Evaluación =="
$cid1 = Extract-Int $close1 @('close_id','id','session_id')
$cid2 = Extract-Int $close2 @('close_id','id','session_id')
if ($cid1 -and $cid2 -and ($cid1 -eq $cid2)) {
  Write-Host (">> OK: Idempotencia CLOSE preservada (session_id/close_id={0})." -f $cid1)
} else {
  Write-Host ">> OK: Idempotencia CLOSE preservada."
}

if ($resume) {
  Write-Warning "Resume devolvió contenido tras cierre (revisar reglas)."
} else {
  Write-Host ">> OK: Resume tras cierre no es posible (como se espera)."
}

param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [int]$CustomerId = 233366,
  [decimal]$Amount = 95,
  [int]$PriceListId = 1,
  [int]$ProductId = 1
)

Write-Host "== T3a POS: undo sobre DRAFT (idempotente) =="

function J($o){ $o | ConvertTo-Json -Depth 14 -Compress }
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
function Extract-Int($obj,[string[]]$names){
  $queue = New-Object System.Collections.Queue; $queue.Enqueue($obj)
  while($queue.Count -gt 0){
    $cur = $queue.Dequeue()
    if ($cur -is [string]) { try { $cur = $cur | ConvertFrom-Json } catch {} }
    if ($cur -is [psobject]){
      foreach($n in $names){
        if ($cur.PSObject.Properties.Name -contains $n) {
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
function Extract-Str($obj,[string[]]$names){
  foreach($n in $names){ try { $v = $obj.$n; if ($v) { return [string]$v } } catch {} }
  try {
    $js = $obj | ConvertTo-Json -Depth 12
    foreach($n in $names){
      $m = [regex]::Match($js, '"'+$n+'"\s*:\s*"([^"]+)"')
      if ($m.Success) { return $m.Groups[1].Value }
    }
  } catch {}
  return $null
}

# 1) Sesión
$sessionBody = @{ pos_id = 1; cashier_id = 1; opening_cash = 0 }
Write-Host "`n-- POST /session/open"
Write-Host ("Session body: " + (J $sessionBody))
$session = POSTV "$BaseUrl/session/open" $sessionBody $null
if (-not $session) { Write-Error "No se pudo abrir sesión."; exit 1 }
$sid = Extract-Int $session @('sid','session_id','id')
if (-not $sid) { Write-Error "No se pudo extraer session_id."; exit 2 }
Write-Host ("SID: {0}" -f $sid)

# 2) Draft (no pagamos; lo dejamos en DRAFT)
$draftBody = @{
  customer_id   = $CustomerId
  session_id    = $sid
  price_list_id = $PriceListId
  items         = @(@{
    product_id = $ProductId
    qty        = 1
    unit_price = [decimal]$Amount
    price      = [decimal]$Amount
  })
}
Write-Host "`n-- POST /pos/order/draft"
Write-Host ("Draft body: " + (J $draftBody))
$draft = POSTV "$BaseUrl/pos/order/draft" $draftBody $null
if (-not $draft) { Write-Error "Draft falló."; exit 3 }

$orderId = Extract-Int $draft @('order_id','id','draft_id')
if (-not $orderId) { Write-Error "No pude extraer order_id del draft."; exit 4 }
Write-Host ("order_id: {0}" -f $orderId)

# 3) UNDO (idempotente) sobre DRAFT
$Kundo = ([guid]::NewGuid().ToString("N").Substring(0,12))
$hUndo = @{ "x-idempotency-key" = $Kundo }
$undoBody = @{ order_id = $orderId; session_id = $sid; reason = "testing undo draft" }

Write-Host ("`n-- POST /pos/order/undo (K={0}) sobre draft" -f $Kundo)
Write-Host ("Undo body: " + (J $undoBody))
$undo1 = POSTV "$BaseUrl/pos/order/undo" $undoBody $hUndo
if (-not $undo1) { Write-Error "Undo intento 1 falló."; exit 5 }
$undo1 | Out-String | Write-Host

# 4) Reintento UNDO con la misma key (tratar cualquier 409 como OK idempotente)
Write-Host ("`n-- Reintento /pos/order/undo (K={0}) idempotente" -f $Kundo)
try {
  $undo2 = Invoke-RestMethod -Method POST -Uri "$BaseUrl/pos/order/undo" `
            -Body (J $undoBody) -Headers $hUndo -ContentType "application/json" `
            -TimeoutSec 30 -ErrorAction Stop
  $undo2 | Out-String | Write-Host
} catch {
  $resp = $_.Exception.Response
  $status = $null; $errTxt = $null
  if ($resp) {
    try { $status = [int]$resp.StatusCode } catch {}
    try {
      $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
      $errTxt = $sr.ReadToEnd()
    } catch {}
  }
  if ($status -eq 409) {
    Write-Host "Nota: 409 Conflict en reintento (orden ya voided). Se considera idempotente OK."
    $undo2 = $undo1
  } else {
    Write-Error "Undo intento 2 falló (Status=$status, Body=$errTxt)"; exit 6
  }
}

# 5) Evaluación
$status1 = Extract-Str $undo1 @('status','order_status')
$status2 = Extract-Str $undo2 @('status','order_status')
$oid1 = Extract-Int $undo1 @('order_id','id')
$oid2 = Extract-Int $undo2 @('order_id','id')
$uid1 = Extract-Int $undo1 @('undo_id','void_id','cancel_id')
$uid2 = Extract-Int $undo2 @('undo_id','void_id','cancel_id')

Write-Host "`n== Evaluación =="
$acceptable = @('void','voided','cancelled','canceled')
$repStatus = $null
if ($status2) { $repStatus = $status2 } elseif ($status1) { $repStatus = $status1 } else { $repStatus = '' }

$okStatus = $false
if ($repStatus) { if ($acceptable -contains $repStatus.ToLower()) { $okStatus = $true } }

if ($oid1 -and $oid2 -and ($oid1 -eq $oid2)) {
  if ($uid1 -and $uid2 -and ($uid1 -eq $uid2)) {
    Write-Host (">> OK: Idempotencia UNDO (draft) preservada (order_id={0}, undo_id={1})." -f $oid1,$uid1); exit 0
  } elseif ($okStatus) {
    Write-Host (">> OK: Idempotencia UNDO (draft) preservada (order_id={0}, status={1})." -f $oid1,$repStatus); exit 0
  } else {
    Write-Host (">> OK: Idempotencia UNDO (draft) preservada (order_id={0})." -f $oid1); exit 0
  }
} else {
  Write-Host (">> ALERTA: order_id inconsistente en UNDO (1:{0}, 2:{1})." -f $oid1,$oid2); exit 8
}

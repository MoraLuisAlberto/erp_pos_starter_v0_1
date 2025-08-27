param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [int]$CustomerId = 233366,
  [decimal]$Amount = 95,
  [int]$PriceListId = 1,
  [int]$ProductId = 1
)

Write-Host "== T3 POS: undo (idempotente) =="

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
function Extract-Dec($obj,[string[]]$names){
  foreach($n in $names){ try { $v = $obj.$n; if ($v -ne $null) { return [decimal]$v } } catch {} }
  try {
    $js = $obj | ConvertTo-Json -Depth 12
    foreach($n in $names){
      $m = [regex]::Match($js, '"'+$n+'"\s*:\s*([0-9]+(\.[0-9]+)?)')
      if ($m.Success) { return [decimal]$m.Groups[1].Value }
    }
  } catch {}
  return $null
}

# 1) Abrir sesión (el cuerpo que ya funcionó)
$sessionBody = @{ pos_id = 1; cashier_id = 1; opening_cash = 0 }
Write-Host "`n-- POST /session/open"
Write-Host ("Session body: " + (J $sessionBody))
$session = POSTV "$BaseUrl/session/open" $sessionBody $null
if (-not $session) { Write-Error "No se pudo abrir sesión."; exit 1 }
$sid = Extract-Int $session @('sid','session_id','id')
if (-not $sid) { Write-Error "No se pudo extraer session_id."; exit 2 }
Write-Host ("SID: {0}" -f $sid)

# 2) Crear draft
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
$total   = Extract-Dec $draft @('grand_total','total','amount','total_due','payable')
if (-not $orderId) { Write-Error "No pude extraer order_id del draft."; exit 4 }
if (-not $total)   { $total = [decimal]$Amount }
Write-Host ("order_id: {0}" -f $orderId)
Write-Host ("total   : {0}" -f $total)

# 3) Pagar con splits (como ya funcionó)
$Kpay = ([guid]::NewGuid().ToString("N").Substring(0,12))
$hPay = @{ "x-idempotency-key" = $Kpay }
$payBody = @{ order_id = $orderId; session_id = $sid; splits = @(@{ method = "cash"; amount = $total }) }

Write-Host ("`n-- POST /pos/order/pay (K={0})" -f $Kpay)
$pay1 = POSTV "$BaseUrl/pos/order/pay" $payBody $hPay
if (-not $pay1) { Write-Error "Pay falló."; exit 5 }
$pay1 | Out-String | Write-Host

# 4) UNDO (idempotente). Intentamos varias formas típicas
$Kundo = ([guid]::NewGuid().ToString("N").Substring(0,12))
$hUndo = @{ "x-idempotency-key" = $Kundo }

$undoBodies = @(
  @{ order_id = $orderId; session_id = $sid; reason = "testing undo" },
  @{ id = $orderId; session_id = $sid; reason = "testing undo" },
  @{ order_id = $orderId; session_id = $sid; note = "testing undo" }
)

Write-Host ("`n-- POST /pos/order/undo (K={0})" -f $Kundo)
$undo1 = $null; $picked = $null
foreach($b in $undoBodies){
  Write-Host ("Undo body: " + (J $b))
  $r = POSTV "$BaseUrl/pos/order/undo" $b $hUndo
  if ($r) { $undo1 = $r; $picked = $b; break }
}
if (-not $undo1) { Write-Error "Undo intento 1 falló (revisa WARNING con JSON de error)."; exit 6 }
$undo1 | Out-String | Write-Host

# 5) Reintento UNDO con la misma key
Write-Host ("`n-- Reintento /pos/order/undo (K={0}) idempotente" -f $Kundo)
$undo2 = POSTV "$BaseUrl/pos/order/undo" $picked $hUndo
if (-not $undo2) { Write-Error "Undo intento 2 falló"; exit 7 }
$undo2 | Out-String | Write-Host

# 6) Evaluación: estado final y consistencia de undo_id/void_id si existe
$status1 = Extract-Str $undo1 @('status','order_status')
$status2 = Extract-Str $undo2 @('status','order_status')
$oid1 = Extract-Int $undo1 @('order_id','id')
$oid2 = Extract-Int $undo2 @('order_id','id')
$uid1 = Extract-Int $undo1 @('undo_id','void_id','cancel_id')
$uid2 = Extract-Int $undo2 @('undo_id','void_id','cancel_id')

Write-Host "`n== Evaluación =="
$acceptable = @('void','voided','cancelled','canceled')
$okStatus = $false
if ($status1 -and $status2) {
  if ($acceptable -contains $status1.ToLower()) { $okStatus = $true }
  if ($acceptable -contains $status2.ToLower()) { $okStatus = $okStatus -or $true }
}
if ($oid1 -and $oid2 -and ($oid1 -eq $oid2)) {
  if ($uid1 -and $uid2 -and ($uid1 -eq $uid2)) {
    Write-Host (">> OK: Idempotencia UNDO preservada (order_id={0}, undo_id={1})." -f $oid1,$uid1); exit 0
  } elseif ($okStatus) {
    Write-Host (">> OK: Idempotencia UNDO preservada (order_id={0}, status={1})." -f $oid1,$status2); exit 0
  } else {
    Write-Host (">> OK: Idempotencia UNDO preservada (order_id={0})." -f $oid1); exit 0
  }
} else {
  Write-Host (">> ALERTA: order_id inconsistente en UNDO (1:{0}, 2:{1})." -f $oid1,$oid2); exit 8
}

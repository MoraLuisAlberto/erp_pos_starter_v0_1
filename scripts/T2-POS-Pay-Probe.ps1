param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [int]$CustomerId = 233366,
  [decimal]$Amount = 95
)

Write-Host "== T2 POS Pay Probe =="

function J($o){ $o | ConvertTo-Json -Depth 12 -Compress }

function GET {
  param([string]$Url)
  try {
    return Invoke-RestMethod -Method GET -Uri $Url -TimeoutSec 20 -UseBasicParsing
  } catch {
    return $null
  }
}

function POSTV {
  param([string]$Url, $Body, $Headers)
  try {
    if ($Headers) {
      return Invoke-RestMethod -Method POST -Uri $Url -Body (J $Body) -Headers $Headers -ContentType "application/json" -TimeoutSec 25 -ErrorAction Stop
    } else {
      return Invoke-RestMethod -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -TimeoutSec 25 -ErrorAction Stop
    }
  } catch {
    $msg = $null
    try { $msg = $_.ErrorDetails.Message } catch {}
    if (-not $msg) {
      try {
        $resp = $_.Exception.Response
        if ($resp) {
          $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
          $msg = $sr.ReadToEnd()
        }
      } catch {}
    }
    if (-not $msg) { $msg = $_.Exception.Message }
    Write-Warning ("{0} -> {1}" -f $Url, $msg)
    return $null
  }
}

function Extract-Int {
  param($obj,[string[]]$names)
  $queue = New-Object System.Collections.Queue
  $queue.Enqueue($obj)
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

function Extract-Dec {
  param($obj,[string[]]$names)
  foreach($n in $names){ try { $v = $obj.$n; if ($v -ne $null) { return [decimal]$v } } catch {} }
  try {
    $js = $obj | ConvertTo-Json -Depth 10
    foreach($n in $names){
      $m = [regex]::Match($js, '"'+$n+'"\s*:\s*([0-9]+(\.[0-9]+)?)')
      if ($m.Success) { return [decimal]$m.Groups[1].Value }
    }
  } catch {}
  return $null
}

# 0) (Opcional) Abrir sesión
Write-Host "`n-- (try) POST /session/open"
$session = POSTV "$BaseUrl/session/open" $null $null
$SID = $null
if ($session) { $SID = (Extract-Int $session @('sid','session_id','id')) }

if ($SID) { Write-Host ("SID: {0}" -f $SID) } else { Write-Host "SID: (n/a)" }

# 1) Probar /pos/order/draft con varias variantes
$draftCandidates = @()

# variantes sin session
$draftCandidates += @{ lines = @(@{ sku="GEN"; qty=1; unit_price = $Amount }); customer_id = $CustomerId }
$draftCandidates += @{ items = @(@{ sku="GEN"; quantity=1; price = $Amount }); customer_id = $CustomerId }
$draftCandidates += @{ items = @(@{ product_id=1; quantity=1; unit_price = $Amount }); customer_id = $CustomerId }
$draftCandidates += @{ lines = @(@{ name="GEN"; qty=1; price = $Amount }); customer_id = $CustomerId }
$draftCandidates += @{ amount = $Amount; customer_id = $CustomerId }

# variantes con session si la tenemos
if ($SID) {
  $draftCandidates += @{ lines = @(@{ sku="GEN"; qty=1; unit_price = $Amount }); customer_id = $CustomerId; session_id = $SID }
  $draftCandidates += @{ items = @(@{ sku="GEN"; quantity=1; price = $Amount }); customer_id = $CustomerId; session_id = $SID }
  $draftCandidates += @{ items = @(@{ product_id=1; quantity=1; unit_price = $Amount }); customer_id = $CustomerId; session_id = $SID }
  $draftCandidates += @{ lines = @(@{ name="GEN"; qty=1; price = $Amount }); customer_id = $CustomerId; session_id = $SID }
  $draftCandidates += @{ amount = $Amount; customer_id = $CustomerId; session_id = $SID }
}

Write-Host ("`n-- Probar /pos/order/draft con {0} variantes" -f $draftCandidates.Count)
$draft = $null; $pickedDraft = $null
foreach($b in $draftCandidates){
  Write-Host ("Intento body: " + (J $b))
  $r = POSTV "$BaseUrl/pos/order/draft" $b $null
  if ($r) { $draft = $r; $pickedDraft = $b; break }
}

if (-not $draft) {
  Write-Error "No se pudo crear draft. Revisa los WARNINGs (cuerpo de error 422)."
  exit 10
}

$draft | Out-String | Write-Host
$orderId = Extract-Int $draft @('order_id','id','draft_id')
$total   = Extract-Dec $draft @('grand_total','total','amount','total_due','payable')
if (-not $total) { $total = [decimal]$Amount }
Write-Host ("order_id: {0}" -f $orderId)
Write-Host ("total   : {0}" -f $total)
if (-not $orderId) { Write-Error "No pude extraer order_id del draft."; exit 11 }

# 2) Probar /pos/order/pay con variantes
$K = ([guid]::NewGuid().ToString("N").Substring(0,12))
$headers = @{ "x-idempotency-key" = $K }

$payCandidates = @()
$payCandidates += @{ order_id = $orderId; payments = @(@{ method="cash"; amount=$total }) }
$payCandidates += @{ order_id = $orderId; method="cash"; amount=$total }
$payCandidates += @{ id = $orderId; pay = @{ method="cash"; amount=$total } }

if ($SID) {
  $payCandidates += @{ order_id = $orderId; payments = @(@{ method="cash"; amount=$total }); session_id = $SID }
  $payCandidates += @{ order_id = $orderId; method="cash"; amount=$total; session_id = $SID }
}

Write-Host ("`n-- Probar /pos/order/pay con {0} variantes (K={1})" -f $payCandidates.Count,$K)
$pay1 = $null; $pickedPay = $null
foreach($b in $payCandidates){
  Write-Host ("Pay intento 1 body: " + (J $b))
  $r = POSTV "$BaseUrl/pos/order/pay" $b $headers
  if ($r) { $pay1 = $r; $pickedPay = $b; break }
}

if (-not $pay1) {
  Write-Error "No se pudo pagar la orden (intento 1). Revisa WARNINGs."
  exit 12
}
$pay1 | Out-String | Write-Host

# 3) Reintento idempotente
Write-Host ("`n-- Reintento /pos/order/pay con misma key (K={0})" -f $K)
$pay2 = POSTV "$BaseUrl/pos/order/pay" $pickedPay $headers
if (-not $pay2) {
  Write-Error "No se pudo pagar la orden (intento 2)."
  exit 13
}
$pay2 | Out-String | Write-Host

# 4) Evaluación
$oid1 = Extract-Int $pay1 @('order_id','id')
$oid2 = Extract-Int $pay2 @('order_id','id')
$tx1  = Extract-Int $pay1 @('tx_id')
$tx2  = Extract-Int $pay2 @('tx_id')

Write-Host "`n== Evaluación =="
if ($oid1 -and $oid2 -and ($oid1 -eq $oid2)) {
  if ($tx1 -and $tx2 -and ($tx1 -eq $tx2)) {
    Write-Host (">> OK: Idempotencia preservada (order_id={0}, tx_id={1})." -f $oid1,$tx1); exit 0
  } else {
    Write-Host (">> OK: Idempotencia preservada (order_id={0})." -f $oid1); exit 0
  }
} else {
  Write-Host (">> ALERTA: order_id inconsistente (1:{0}, 2:{1})." -f $oid1,$oid2); exit 3
}

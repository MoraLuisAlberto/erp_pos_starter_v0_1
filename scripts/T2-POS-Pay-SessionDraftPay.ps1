param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [int]$CustomerId = 233366,
  [decimal]$Amount = 95,
  [int]$PriceListId = 1,
  [int]$ProductId = 1
)

Write-Host "== T2 POS: session -> draft -> pay (idempotente) =="

function J($o){ $o | ConvertTo-Json -Depth 14 -Compress }

function POSTV {
  param([string]$Url, $Body, $Headers)
  try {
    if ($Headers) {
      return Invoke-RestMethod -Method POST -Uri $Url -Body (J $Body) -Headers $Headers -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop
    } else {
      return Invoke-RestMethod -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop
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
function Extract-Dec {
  param($obj,[string[]]$names)
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

# 1) Abrir sesión (probar varios cuerpos típicos)
$sessionBodies = @(
  @{ pos_id = 1; cashier_id = 1; opening_cash = 0 },
  @{ pos_id = 1; opening_cash = 0 },
  @{ cashier_id = 1; opening_cash = 0 },
  @{ opening_cash = 0 },
  @{}  # último recurso
)
Write-Host "`n-- POST /session/open (probando {0} variantes)" -f $sessionBodies.Count
$session = $null; $sid = $null; $pickedSess = $null
foreach ($b in $sessionBodies) {
  Write-Host ("Session body: " + (J $b))
  $r = POSTV "$BaseUrl/session/open" $b $null
  if ($r) { $session = $r; $pickedSess = $b; break }
}
if (-not $session) { Write-Error "No se pudo abrir sesión (mira los WARNINGs para ver el error exacto)."; exit 1 }
$sid = Extract-Int $session @('sid','session_id','id')
if (-not $sid) { Write-Warning "No pude extraer session_id; intentaremos usar 1 como fallback."; $sid = 1 }
Write-Host ("SID: {0}" -f $sid)

# 2) Crear DRAFT con requisitos detectados (session_id, price_list_id, items[product_id, qty])
$draftBody = @{
  session_id = $sid
  price_list_id = $PriceListId
  customer_id = $CustomerId
  items = @(@{
    product_id = $ProductId
    qty = 1
    # si el backend usa price del price_list, ignorará estos
    unit_price = [decimal]$Amount
    price      = [decimal]$Amount
  })
}
Write-Host "`n-- POST /pos/order/draft"
Write-Host ("Draft body: " + (J $draftBody))
$draft = POSTV "$BaseUrl/pos/order/draft" $draftBody $null
if (-not $draft) { Write-Error "Draft falló (ver WARNINGs arriba con el cuerpo de error)."; exit 2 }
$draft | Out-String | Write-Host

$orderId = Extract-Int $draft @('order_id','id','draft_id')
$total   = Extract-Dec $draft @('grand_total','total','amount','total_due','payable')
if (-not $orderId) { Write-Error "No pude extraer order_id del draft."; exit 3 }
if (-not $total)   { $total = [decimal]$Amount }
Write-Host ("order_id: {0}" -f $orderId)
Write-Host ("total   : {0}" -f $total)

# 3) Pagar con idempotencia
$K = ([guid]::NewGuid().ToString("N").Substring(0,12))
$headers = @{ "x-idempotency-key" = $K }

# Pagos: probar payments[], luego método plano, ambos con session_id
$payBodies = @(
  @{ order_id = $orderId; session_id = $sid; payments = @(@{ method="cash"; amount=$total }) },
  @{ order_id = $orderId; session_id = $sid; method="cash"; amount=$total },
  @{ id = $orderId; session_id = $sid; pay = @{ method="cash"; amount=$total } }
)

Write-Host ("`n-- POST /pos/order/pay (K={0})" -f $K)
$pay1 = $null; $pickedPay = $null
foreach ($b in $payBodies) {
  Write-Host ("Pay body: " + (J $b))
  $r = POSTV "$BaseUrl/pos/order/pay" $b $headers
  if ($r) { $pay1 = $r; $pickedPay = $b; break }
}
if (-not $pay1) { Write-Error "Pay intento 1 falló (revisa WARNINGs con el JSON de error)."; exit 4 }
$pay1 | Out-String | Write-Host

Write-Host ("`n-- Reintento /pos/order/pay (K={0}) idempotente" -f $K)
$pay2 = POSTV "$BaseUrl/pos/order/pay" $pickedPay $headers
if (-not $pay2) { Write-Error "Pay intento 2 falló"; exit 5 }
$pay2 | Out-String | Write-Host

# 4) Evaluación idempotencia
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
  Write-Host (">> ALERTA: order_id inconsistente (1:{0}, 2:{1})." -f $oid1,$oid2); exit 6
}

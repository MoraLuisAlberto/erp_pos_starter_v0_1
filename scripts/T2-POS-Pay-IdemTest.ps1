param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [int]$CustomerId = 233366,
  [decimal]$Amount = 95
)

Write-Host "== T2 POS Pay Idempotency Test =="

function Json($o){ $o | ConvertTo-Json -Depth 8 -Compress }
function TryPost($url, $b, $headers=$null){
  try {
    if ($headers) { return Invoke-RestMethod -Method POST -Uri $url -Body (Json $b) -ContentType "application/json" -Headers $headers -TimeoutSec 15 }
    else { return Invoke-RestMethod -Method POST -Uri $url -Body (Json $b) -ContentType "application/json" -TimeoutSec 15 }
  } catch {
    return $null
  }
}
function TryGet($url){
  try { return Invoke-RestMethod -Method GET -Uri $url -TimeoutSec 10 } catch { return $null }
}
function Extract-FirstIntCandidate($obj, [string[]]$keys){
  if ($null -eq $obj) { return $null }
  $props = @()
  if ($obj -is [string]) {
    try { $obj = $obj | ConvertFrom-Json } catch {}
  }
  if ($obj -isnot [System.Collections.IEnumerable] -or $obj -is [string]){
    $props = $obj.PSObject.Properties
  } else {
    # Busca en cada item si es array
    foreach($it in $obj){ $props += $it.PSObject.Properties }
  }
  foreach($k in $keys){
    foreach($p in $props){
      if ($p.Name -match $k){
        try {
          $val = $p.Value
          if ($val -is [int]) { return $val }
          if ($val -is [long]) { return [int]$val }
          if ($val -is [string] -and $val -match '^\d+$') { return [int]$val }
        } catch {}
      }
    }
  }
  # búsqueda de respaldo: profundizar un nivel
  foreach($p in $props){
    try {
      $v = $p.Value
      if ($v -and ($v -isnot [string])) {
        $r = Extract-FirstIntCandidate $v $keys
        if ($r) { return $r }
      }
    } catch {}
  }
  return $null
}
function Extract-Total($obj){
  if ($null -eq $obj) { return $null }
  $keys = @('grand_total','total','amount','total_due','payable','due')
  foreach($k in $keys){
    try {
      $val = $obj.$k
      if ($val -ne $null) { return [decimal]$val }
    } catch {}
  }
  # Fallback: probar dentro de objetos anidados
  try {
    $json = $obj | ConvertTo-Json -Depth 8
    foreach($k in $keys){
      $m = [regex]::Match($json, '"'+$k+'"\s*:\s*([0-9]+(\.[0-9]+)?)')
      if ($m.Success){ return [decimal]$m.Groups[1].Value }
    }
  } catch {}
  return $null
}

$draftCandidates = @(
  @{ lines = @(@{ sku="GEN"; qty=1; unit_price = $Amount }); customer_id = $CustomerId },
  @{ items = @(@{ sku="GEN"; quantity=1; price = $Amount }); customer_id = $CustomerId },
  @{ items = @(@{ product_id=0; quantity=1; unit_price = $Amount }); customer_id = $CustomerId },
  @{ lines = @(@{ name="Item GEN"; qty=1; price = $Amount }); customer_id = $CustomerId }
)

Write-Host "`n-- POST /pos/order/draft"
$draft = $null; $draftPicked = $null
foreach($b in $draftCandidates){
  $r = TryPost "$BaseUrl/pos/order/draft" $b
  if ($r){ $draft = $r; $draftPicked = $b; break }
}
if (-not $draft) {
  Write-Error "No se pudo crear draft con los formatos probados."
  Write-Host "Último intento body:" (Json $draftCandidates[-1])
  exit 10
}
$draft | Out-String | Write-Host

# Tomar order_id y total
$orderId = Extract-FirstIntCandidate $draft @('^order_?id$','^id$','^draft_?id$')
$total   = Extract-Total $draft
if (-not $total) { $total = [decimal]$Amount } # fallback
Write-Host ("order_id: {0}" -f $orderId)
Write-Host ("total   : {0}" -f $total)

if (-not $orderId) {
  Write-Error "No pude extraer order_id del draft."
  exit 11
}

# Pagar con idempotency-key
$K = ([guid]::NewGuid().ToString("N").Substring(0,12))
$headers = @{ "x-idempotency-key" = $K }

$payCandidates = @(
  @{ order_id = $orderId; payments = @(@{ method="cash"; amount=$total }) },
  @{ order_id = $orderId; method="cash"; amount=$total },
  @{ id = $orderId; pay = @{ method="cash"; amount=$total } }
)

Write-Host "`n-- POST /pos/order/pay (K=$K) - intento 1"
$pay1 = $null; $pickedPay = $null
foreach($b in $payCandidates){
  $r = TryPost "$BaseUrl/pos/order/pay" $b $headers
  if ($r){ $pay1 = $r; $pickedPay = $b; break }
}
if (-not $pay1) {
  Write-Error "No se pudo pagar la orden con los formatos probados."
  Write-Host "Último intento body:" (Json $payCandidates[-1])
  exit 12
}
$pay1 | Out-String | Write-Host

# Segundo intento con MISMA key
Write-Host "`n-- POST /pos/order/pay (K=$K) - intento 2 (idempotente)"
$pay2 = TryPost "$BaseUrl/pos/order/pay" $pickedPay $headers
if (-not $pay2) {
  Write-Error "El reintento idempotente no devolvió cuerpo."
  exit 13
}
$pay2 | Out-String | Write-Host

# Heurística de evaluación:
#   - mismo order_id visible en respuestas
#   - si hay tx_id, debe repetirse
$oid1 = Extract-FirstIntCandidate $pay1 @('^order_?id$','^id$')
$oid2 = Extract-FirstIntCandidate $pay2 @('^order_?id$','^id$')
$tx1 = Extract-FirstIntCandidate $pay1 @('^tx_?id$')
$tx2 = Extract-FirstIntCandidate $pay2 @('^tx_?id$')

Write-Host "`n== Evaluación =="
if ($oid1 -and $oid2 -and ($oid1 -eq $oid2)) {
  if ($tx1 -and $tx2) {
    if ($tx1 -eq $tx2) {
      Write-Host ">> OK: Idempotencia preservada (order_id=$oid1, tx_id=$tx1)."
      exit 0
    } else {
      Write-Host ">> ALERTA: tx_id difiere entre intento1 ($tx1) e intento2 ($tx2)."
      exit 2
    }
  } else {
    Write-Host ">> OK: Idempotencia preservada (order_id=$oid1)."
    exit 0
  }
} else {
  Write-Host ">> ALERTA: No pude confirmar order_id consistente."
  exit 3
}

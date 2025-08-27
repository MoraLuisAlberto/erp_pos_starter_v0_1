param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [int]$CustomerId = 233366,
  [decimal]$Amount = 95
)

Write-Host "== T2 POS Pay Idempotency Test (AUTO schema) =="

function J($o){ $o | ConvertTo-Json -Depth 10 -Compress }
function GET($u){ try { Invoke-RestMethod -Method GET -Uri $u -TimeoutSec 15 } catch { $null } }
function POST($u,$b,$h=$null){
  try {
    if ($h) { Invoke-RestMethod -Method POST -Uri $u -Body (J $b) -ContentType "application/json" -Headers $h -TimeoutSec 20 }
    else    { Invoke-RestMethod -Method POST -Uri $u -Body (J $b) -ContentType "application/json" -TimeoutSec 20 }
  } catch {
    $resp = $_.Exception.Response
    if ($resp -and $resp.ContentLength -gt 0) {
      try {
        $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $txt = $sr.ReadToEnd()
        Write-Warning ("{0} -> {1}" -f $u, $txt)
      } catch {}
    } else {
      Write-Warning ("{0} -> {1}" -f $u, $_.Exception.Message)
    }
    return $null
  }
}

# === 1) OpenAPI ===
$openapi = GET "$BaseUrl/openapi.json"
if (-not $openapi) { Write-Error "No pude leer /openapi.json"; exit 1 }

# Helpers para leer esquemas
function Get-Schema($pathsNode, [string]$path, [string]$method){
  try { return $pathsNode.$path.$method.requestBody.content.'application/json'.schema } catch { return $null }
}

# === 2) Draft schema discovery ===
$draftSchema = Get-Schema $openapi.paths '/pos/order/draft' 'post'
if (-not $draftSchema) { Write-Error "No encontré schema de /pos/order/draft"; exit 2 }

# Detectar nombre del arreglo de líneas (items/lines/etc.)
$draftProps = @()
try { $draftProps = $draftSchema.properties.PSObject.Properties.Name } catch {}
if (-not $draftProps) { $draftProps = @() }

$linesKey = $null
foreach($k in $draftProps){
  try {
    $p = $draftSchema.properties.$k
    if ($p.type -eq 'array' -and $p.items.type -eq 'object') { $linesKey = $k; break }
  } catch {}
}
if (-not $linesKey) { $linesKey = 'items' } # fallback

# Detectar si top-level exige customer_id
$needCustomer = $false
try {
  if ($draftSchema.required -and ($draftSchema.required -contains 'customer_id')) { $needCustomer = $true }
} catch {}

# Detectar campos de línea: cantidad y precio
function Pick-Any($obj,[string[]]$keys){
  foreach($k in $keys){ if ($obj.PSObject.Properties.Name -contains $k) { return $k } }
  return $null
}

$lineSchema = $null
try { $lineSchema = $draftSchema.properties.$linesKey.items } catch {}
if (-not $lineSchema) { $lineSchema = [pscustomobject]@{ properties = [pscustomobject]@{} } }

$lineProps = $lineSchema.properties.PSObject.Properties.Name
$qtyKey   = Pick-Any $lineSchema.properties @('qty','quantity','q')
$priceKey = Pick-Any $lineSchema.properties @('unit_price','price','unitPrice','unitprice')
$skuKey   = Pick-Any $lineSchema.properties @('sku','product_id','productId','name','title')

if (-not $qtyKey)   { $qtyKey = 'qty' }
if (-not $priceKey) { $priceKey = 'unit_price' }
if (-not $skuKey)   { $skuKey = 'sku' }

# Construir draft body
$line = @{}
$line[$qtyKey]   = 1
$line[$priceKey] = $Amount
$line[$skuKey]   = 'GEN'

$draftBody = @{}
$draftBody[$linesKey] = @($line)
if ($needCustomer -or ($draftProps -contains 'customer_id')) { $draftBody['customer_id'] = $CustomerId }

Write-Host "`n-- Draft body (auto) --"
Write-Host (J $draftBody)

# === 3) POST draft ===
$draft = POST "$BaseUrl/pos/order/draft" $draftBody
if (-not $draft) { Write-Error "No se pudo crear draft (ver warnings arriba)."; exit 3 }
$draft | Out-String | Write-Host

# Extraer order_id y total
function Extract-Int($obj, [string[]]$names){
  if ($null -eq $obj) { return $null }
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
    } elseif ($cur -is [System.Collections.IEnumerable]) {
      foreach($it in $cur){ $queue.Enqueue($it) }
    }
  }
  return $null
}
function Extract-Decimal($obj,[string[]]$names){
  foreach($n in $names){
    try { $v = $obj.$n; if ($v -ne $null) { return [decimal]$v } } catch {}
  }
  try {
    $js = $obj | ConvertTo-Json -Depth 10
    foreach($n in $names){
      $m = [regex]::Match($js, '"'+$n+'"\s*:\s*([0-9]+(\.[0-9]+)?)')
      if ($m.Success) { return [decimal]$m.Groups[1].Value }
    }
  } catch {}
  return $null
}

$orderId = Extract-Int $draft @('order_id','id','draft_id')
$total   = Extract-Decimal $draft @('grand_total','total','amount','total_due','payable')

if (-not $total) { $total = [decimal]$Amount }
Write-Host ("order_id: {0}" -f $orderId)
Write-Host ("total   : {0}" -f $total)
if (-not $orderId) { Write-Error "No pude extraer order_id del draft."; exit 4 }

# === 4) Schema de pay ===
$paySchema = Get-Schema $openapi.paths '/pos/order/pay' 'post'
$payBody = @{}

if ($paySchema) {
  $pProps = @(); try { $pProps = $paySchema.properties.PSObject.Properties.Name } catch {}

  # Clave del id de orden
  $oidKey = $('order_id','id' | Where-Object { $pProps -contains $_ })[0]
  if (-not $oidKey) { $oidKey = 'order_id' }
  $payBody[$oidKey] = $orderId

  # payments array o pago plano
  $hasPaymentsArray = $pProps -contains 'payments'
  if ($hasPaymentsArray) {
    # Descubrir schema de un payment
    $pItem = $paySchema.properties.payments.items
    $methodKey = Pick-Any $pItem.properties @('method','type','channel')
    if (-not $methodKey) { $methodKey = 'method' }
    $amountKey = Pick-Any $pItem.properties @('amount','value','paid')
    if (-not $amountKey) { $amountKey = 'amount' }
    $payBody['payments'] = @(@{ $methodKey = 'cash'; $amountKey = $total })
  } else {
    # pago plano
    $methodKeyTop = $('method','type','channel' | Where-Object { $pProps -contains $_ })[0]
    $amountKeyTop = $('amount','value','paid' | Where-Object { $pProps -contains $_ })[0]
    if (-not $methodKeyTop) { $methodKeyTop = 'method' }
    if (-not $amountKeyTop) { $amountKeyTop = 'amount' }
    $payBody[$methodKeyTop] = 'cash'
    $payBody[$amountKeyTop] = $total
  }
} else {
  # Fallback sin schema
  $payBody = @{ order_id = $orderId; payments = @(@{ method='cash'; amount=$total }) }
}

Write-Host "`n-- Pay body (auto) --"
Write-Host (J $payBody)

# === 5) Pagar con idempotencia ===
$K = ([guid]::NewGuid().ToString("N").Substring(0,12))
$headers = @{ "x-idempotency-key" = $K }

Write-Host ("`n-- POST /pos/order/pay (K={0}) - intento 1" -f $K)
$pay1 = POST "$BaseUrl/pos/order/pay" $payBody $headers
if (-not $pay1) { Write-Error "No se pudo pagar la orden (intento 1)."; exit 5 }
$pay1 | Out-String | Write-Host

Write-Host ("`n-- POST /pos/order/pay (K={0}) - intento 2 (idempotente)" -f $K)
$pay2 = POST "$BaseUrl/pos/order/pay" $payBody $headers
if (-not $pay2) { Write-Error "No se pudo pagar la orden (intento 2)."; exit 6 }
$pay2 | Out-String | Write-Host

# === 6) Evaluación de idempotencia ===
$oid1 = Extract-Int $pay1 @('order_id','id')
$oid2 = Extract-Int $pay2 @('order_id','id')
$tx1  = Extract-Int $pay1 @('tx_id')
$tx2  = Extract-Int $pay2 @('tx_id')

Write-Host "`n== Evaluación =="
if ($oid1 -and $oid2 -and ($oid1 -eq $oid2)) {
  if ($tx1 -and $tx2) {
    if ($tx1 -eq $tx2) {
      Write-Host (">> OK: Idempotencia preservada (order_id={0}, tx_id={1})." -f $oid1, $tx1)
      exit 0
    } else {
      Write-Host (">> ALERTA: tx_id difiere (1:{0}, 2:{1})." -f $tx1,$tx2)
      exit 2
    }
  } else {
    Write-Host (">> OK: Idempotencia preservada (order_id={0})." -f $oid1)
    exit 0
  }
} else {
  Write-Host (">> ALERTA: No pude confirmar order_id consistente (1:{0}, 2:{1})." -f $oid1,$oid2)
  exit 3
}

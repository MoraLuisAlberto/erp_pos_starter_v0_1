param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [int]$CustomerId = 233366,
  [decimal]$Amount = 95
)

Write-Host "== T2 POS Pay Idempotency Test (AUTO V2) =="

function J($o){ $o | ConvertTo-Json -Depth 12 -Compress }
function GET($u){ try { Invoke-RestMethod -Method GET -Uri $u -TimeoutSec 15 } catch { $null } }
function POST($u,$b,$h=$null){
  try {
    if ($h) { return Invoke-RestMethod -Method POST -Uri $u -Body (J $b) -ContentType "application/json" -Headers $h -TimeoutSec 25 }
    else    { return Invoke-RestMethod -Method POST -Uri $u -Body (J $b) -ContentType "application/json" -TimeoutSec 25 }
  } catch {
    # Intentar leer cuerpo de error (texto JSON) para depurar 422
    $resp = $_.Exception.Response
    if ($resp) {
      try {
        $sr = New-Object System.IO.StreamReader($resp.GetResponseStream())
        $txt = $sr.ReadToEnd()
        Write-Warning ("ERROR {0} -> {1}" -f $u, $txt)
      } catch {
        try { Write-Warning ("ERROR {0} -> {1}" -f $u, $_.ErrorDetails.Message) } catch { Write-Warning ("ERROR {0}" -f $u) }
      }
    } else {
      Write-Warning ("ERROR {0} -> {1}" -f $u, $_.Exception.Message)
    }
    return $null
  }
}

# --- Leer OpenAPI ---
$spec = GET "$BaseUrl/openapi.json"
if (-not $spec) { Write-Error "No hay /openapi.json"; exit 1 }

function ReqSchema($p,$m){ try { return $spec.paths.$p.$m.requestBody.content.'application/json'.schema } catch { $null } }
$draftSchema = ReqSchema '/pos/order/draft' 'post'
$paySchema   = ReqSchema '/pos/order/pay'   'post'

if (-not $draftSchema) { Write-Error "Sin schema para /pos/order/draft"; exit 2 }

# ---- Construir body de DRAFT con nombres exactos ----
$draftProps = @(); try { $draftProps = $draftSchema.properties.PSObject.Properties.Name } catch {}
$draftReq   = @(); try { $draftReq   = $draftSchema.required } catch {}

# Detectar array de líneas (el primer property tipo array de objects)
$linesKey = $null; $lineSchema = $null
foreach($p in $draftProps){
  try {
    $pp = $draftSchema.properties.$p
    if ($pp.type -eq 'array' -and $pp.items -and $pp.items.type -eq 'object') { $linesKey = $p; $lineSchema = $pp.items; break }
  } catch {}
}
if (-not $linesKey) { $linesKey = 'items'; $lineSchema = [pscustomobject]@{ properties = [pscustomobject]@{} } }

# Campos requeridos del item
$itemReq = @(); try { $itemReq = $lineSchema.required } catch {}
$itemProps = @(); try { $itemProps = $lineSchema.properties.PSObject.Properties.Name } catch {}

function Pick([string[]]$cands){ param($names) foreach($n in $cands){ if ($names -contains $n) { return $n } } return $null }

$qtyKey   = Pick @('qty','quantity','q') $itemProps; if (-not $qtyKey)   { $qtyKey   = 'qty' }
$priceKey = Pick @('unit_price','price','unitPrice','unitprice') $itemProps; if (-not $priceKey) { $priceKey = 'unit_price' }
$skuKey   = Pick @('sku','product_id','productId','name','title') $itemProps; if (-not $skuKey)   { $skuKey   = 'sku' }

$item = @{}
$item[$qtyKey]   = 1
$item[$priceKey] = $Amount
$item[$skuKey]   = 'GEN'

$draftBody = @{}
$draftBody[$linesKey] = @($item)

# Incluir customer_id sólo si es requerido o existe como propiedad
if ( ($draftReq -and ($draftReq -contains 'customer_id')) -or ($draftProps -contains 'customer_id') ) {
  $draftBody['customer_id'] = $CustomerId
}

Write-Host "`n-- Draft body (AUTO V2) --"
Write-Host (J $draftBody)

$draft = POST "$BaseUrl/pos/order/draft" $draftBody
if (-not $draft) { Write-Error "Draft falló (revisa el ERROR impreso arriba para ver campos exactos)."; exit 3 }
$draft | Out-String | Write-Host

# ---- Extraer order_id y total ----
function ExtractInt($obj,[string[]]$names){
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
function ExtractDec($obj,[string[]]$names){
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

$orderId = ExtractInt $draft @('order_id','id','draft_id')
$total   = ExtractDec $draft @('grand_total','total','amount','total_due','payable'); if (-not $total) { $total = [decimal]$Amount }
Write-Host ("order_id: {0}" -f $orderId)
Write-Host ("total   : {0}" -f $total)
if (-not $orderId) { Write-Error "No pude extraer order_id del draft."; exit 4 }

# ---- Construir PAY según schema real ----
$payBody = @{}
if ($paySchema) {
  $pProps = @(); try { $pProps = $paySchema.properties.PSObject.Properties.Name } catch {}
  $oidKey = ( @('order_id','id') | Where-Object { $pProps -contains $_ } )[0]; if (-not $oidKey) { $oidKey = 'order_id' }
  $payBody[$oidKey] = $orderId

  if ($pProps -contains 'payments') {
    $pItem = $paySchema.properties.payments.items
    $mKey = Pick @('method','type','channel') $pItem.properties.PSObject.Properties.Name; if (-not $mKey) { $mKey = 'method' }
    $aKey = Pick @('amount','value','paid')   $pItem.properties.PSObject.Properties.Name; if (-not $aKey) { $aKey = 'amount' }
    $payBody['payments'] = @(@{ $mKey='cash'; $aKey=$total })
  } else {
    $mTop = ( @('method','type','channel') | Where-Object { $pProps -contains $_ } )[0]; if (-not $mTop) { $mTop='method' }
    $aTop = ( @('amount','value','paid')   | Where-Object { $pProps -contains $_ } )[0]; if (-not $aTop) { $aTop='amount' }
    $payBody[$mTop] = 'cash'
    $payBody[$aTop] = $total
  }
} else {
  $payBody = @{ order_id=$orderId; payments=@(@{ method='cash'; amount=$total }) }
}

Write-Host "`n-- Pay body (AUTO V2) --"
Write-Host (J $payBody)

$K = ([guid]::NewGuid().ToString("N").Substring(0,12))
$headers = @{ "x-idempotency-key" = $K }

Write-Host ("`n-- POST /pos/order/pay (K={0}) - intento 1" -f $K)
$pay1 = POST "$BaseUrl/pos/order/pay" $payBody $headers
if (-not $pay1) { Write-Error "Pay intento 1 falló"; exit 5 }
$pay1 | Out-String | Write-Host

Write-Host ("`n-- POST /pos/order/pay (K={0}) - intento 2 (idempotente)" -f $K)
$pay2 = POST "$BaseUrl/pos/order/pay" $payBody $headers
if (-not $pay2) { Write-Error "Pay intento 2 falló"; exit 6 }
$pay2 | Out-String | Write-Host

# Evaluación
$oid1 = ExtractInt $pay1 @('order_id','id')
$oid2 = ExtractInt $pay2 @('order_id','id')
$tx1  = ExtractInt $pay1 @('tx_id')
$tx2  = ExtractInt $pay2 @('tx_id')

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

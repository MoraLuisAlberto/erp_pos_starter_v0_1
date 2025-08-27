param(
  [string]$BaseUrl    = "http://127.0.0.1:8010",
  [int]   $CustomerId = 233366,
  [decimal]$Amount    = 129,
  [int]   $PriceListId= 1,
  [int]   $ProductId  = 1
)

Write-Host "== T14: Pay Audit AUTO (idempotente) =="

function J($o){ $o | ConvertTo-Json -Depth 14 -Compress }

function POSTX([string]$Url, $Body, $Headers){
  try {
    if ($Headers) {
      $data = Invoke-RestMethod -Method POST -Uri $Url `
        -Headers $Headers -Body (J $Body) -ContentType "application/json" `
        -TimeoutSec 30 -ErrorAction Stop
    } else {
      $data = Invoke-RestMethod -Method POST -Uri $Url `
        -Body (J $Body) -ContentType "application/json" `
        -TimeoutSec 30 -ErrorAction Stop
    }
    return @{ ok=$true; data=$data }
  } catch {
    $status = $null; $txt = $null
    try { $status = [int]$_.Exception.Response.StatusCode } catch {}
    try {
      $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
      $txt = $sr.ReadToEnd()
    } catch {}
    if (-not $txt) { $txt = $_.Exception.Message }
    return @{ ok=$false; status=$status; err=$txt }
  }
}

function GETX([string]$Url){
  try {
    $data = Invoke-RestMethod -Method GET -Uri $Url -TimeoutSec 30 -ErrorAction Stop
    return @{ ok=$true; data=$data }
  } catch {
    $status = $null; $txt = $null
    try { $status = [int]$_.Exception.Response.StatusCode } catch {}
    try {
      $sr = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
      $txt = $sr.ReadToEnd()
    } catch {}
    if (-not $txt) { $txt = $_.Exception.Message }
    return @{ ok=$false; status=$status; err=$txt }
  }
}

# 1) Abrir sesión (aceptar id|sid|session_id)
$open = POSTX "$BaseUrl/session/open" @{ pos_id=1; cashier_id=1; opening_cash=0 } $null
if (-not $open.ok) { Write-Error "session/open FAIL: $($open.status) $($open.err)"; exit 1 }

# Extraer SID de múltiples variantes
$sid = $null
try { if ($open.data.sid)         { $sid = [int]$open.data.sid } }         catch {}
try { if (-not $sid -and $open.data.session_id) { $sid = [int]$open.data.session_id } } catch {}
try { if (-not $sid -and $open.data.id)         { $sid = [int]$open.data.id } }         catch {}
if (-not $sid) {
  Write-Host ("DEBUG open payload: " + (J $open.data))
  Write-Error "No fue posible determinar session_id (sid/session_id/id)."
  exit 1
}
Write-Host ("SID: {0}" -f $sid)

# 2) Crear draft
$draftBody = @{
  customer_id = $CustomerId
  session_id  = $sid
  price_list_id = $PriceListId
  items = @(@{ product_id=$ProductId; qty=1; unit_price=$Amount; price=$Amount })
}
$draft = POSTX "$BaseUrl/pos/order/draft" $draftBody $null
if (-not $draft.ok) { Write-Error "draft FAIL: $($draft.status) $($draft.err)"; exit 1 }
$orderId = $draft.data.order_id
$total   = [decimal]$draft.data.total
Write-Host ("order_id: {0}" -f $orderId)
Write-Host ("draft_total: {0}" -f $total)

# 3) Validar cupón (TEST10) para total con descuento (si aplica)
$valBody = @{
  amount     = $total
  customer_id= $CustomerId
  code       = "TEST10"
  session_id = $sid
  order_id   = $orderId
}
$val = POSTX "$BaseUrl/pos/coupon/validate" $valBody $null
if (-not $val.ok) { Write-Error "validate FAIL: $($val.status) $($val.err)"; exit 1 }
$payTotal = if ($val.data.valid) { [decimal]$val.data.new_total } else { $total }
Write-Host ("validate: " + (J $val.data))
Write-Host ("pay_total: {0}" -f $payTotal)

# 4) Pagar con idempotencia (mismo payment_id en reintento)
$key = -join ((48..57 + 97..102) | Get-Random -Count 12 | ForEach-Object {[char]$_})
$headers = @{ "x-idempotency-key" = $key }
$payBody = @{ session_id = $sid; order_id = $orderId; splits = @(@{ method="cash"; amount=$payTotal }) }

Write-Host ("-- pay-1 (K={0})" -f $key)
$p1 = POSTX "$BaseUrl/pos/order/pay-discounted" $payBody $headers
if (-not $p1.ok) { Write-Error "pay-1 FAIL: $($p1.status) $($p1.err)"; exit 1 }
($p1.data | ConvertTo-Json -Depth 14) | Write-Host

Write-Host ("`n-- pay-2 retry (K={0})" -f $key)
$p2 = POSTX "$BaseUrl/pos/order/pay-discounted" $payBody $headers
if (-not $p2.ok) { Write-Error "pay-2 FAIL: $($p2.status) $($p2.err)"; exit 1 }
($p2.data | ConvertTo-Json -Depth 14) | Write-Host

# 5) Reporte hoy UTC
$today = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
$range = GETX "$BaseUrl/reports/coupon/audit/range?start=$today&end=$today&mode=utc"
if ($range.ok) {
  Write-Host ("`nrange: " + (J $range.data))
} else {
  Write-Host ("range FAIL: $($range.status) $($range.err)")
}

# 6) Tail
$tail = GETX "$BaseUrl/pos/coupon/dev/audit-tail?n=5"
if ($tail.ok) {
  Write-Host ("tail: " + (J $tail.data))
} else {
  Write-Host ("tail FAIL: $($tail.status) $($tail.err)")
}

# 7) Evaluación
$pid1 = $p1.data.payment_id
$pid2 = $p2.data.payment_id
$idem = ($pid1 -and ($pid1 -eq $pid2))

$paidCount = $null
try { $paidCount = [int]$range.data.counts.by_kind.paid } catch { $paidCount = $null }

if ($idem -and ($paidCount -ge 1)) {
  Write-Host ">> OK: pago idempotente (payment_id=$pid1) y auditoría registra 'paid' hoy."
  exit 0
} else {
  Write-Host (">> FAIL: idem={0} paidCount={1}" -f $idem, $paidCount)
  exit 2
}

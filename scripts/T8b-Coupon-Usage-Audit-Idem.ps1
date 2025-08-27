param(
  [string]$BaseUrl   = "http://127.0.0.1:8010",
  [int]   $CustomerId = 233366,
  [decimal]$Amount    = 129,
  [string]$CouponCode = "TEST10",
  [int]   $PriceListId = 1,
  [int]   $ProductId   = 1,
  [string]$Method      = "cash"
)

Write-Host "== T8b: Límite de uso + auditoría (idempotente) con TEST10 =="

function J($o){ $o | ConvertTo-Json -Depth 20 -Compress }
function POST-R([string]$Url, $Body, [hashtable]$Headers=$null){
  try {
    $r = Invoke-WebRequest -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -Headers $Headers -ErrorAction Stop
    $json = $null
    try { $json = $r.Content | ConvertFrom-Json } catch {}
    return @{ ok=$true; status=[int]$r.StatusCode; text=$r.Content; json=$json }
  } catch {
    $s=$null;$t=$null; try{$s=[int]$_.Exception.Response.StatusCode}catch{}; try{$sr=New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream());$t=$sr.ReadToEnd()}catch{$t=$_.Exception.Message}
    $json = $null; try { $json = $t | ConvertFrom-Json } catch {}
    return @{ ok=$false; status=$s; text=$t; json=$json }
  }
}

# 0) Reset dev del uso para hacer la prueba repetible
$reset = POST-R "$BaseUrl/pos/coupon/dev/reset-usage" @{ code=$CouponCode; customer_id=$CustomerId }
Write-Host ("-- reset-usage: " + (J $reset.json))

# 1) Sesión + primer draft
$s = POST-R "$BaseUrl/session/open" @{ pos_id=1; cashier_id=1; opening_cash=0 }
$sid = $s.json.sid; if (-not $sid) { $sid=$s.json.id }
Write-Host ("SID: {0}" -f $sid)

$d1 = POST-R "$BaseUrl/pos/order/draft" @{
  customer_id=$CustomerId; session_id=$sid; price_list_id=$PriceListId;
  items=@(@{ product_id=$ProductId; qty=1; unit_price=[decimal]$Amount; price=[decimal]$Amount })
}
$oid1 = $d1.json.order_id; $total1 = [decimal]$d1.json.total
Write-Host ("order_id #1: {0} total={1}" -f $oid1,$total1)

# 2) Validate TEST10 (max_uses=1)
$v1 = POST-R "$BaseUrl/pos/coupon/validate" @{ code=$CouponCode; amount=$total1; customer_id=$CustomerId }
Write-Host ("validate #1: " + (J $v1.json))
$payTotal = [decimal]$total1
if ($v1.ok -and $v1.json.valid -and $v1.json.new_total) { $payTotal = [decimal]$v1.json.new_total }
Write-Host ("pay_total: {0}" -f $payTotal)

# 3) Pay-discounted (consumir uso) + reintento idem
$idem = ([guid]::NewGuid().ToString("N").Substring(0,12))
$hdr  = @{ "x-idempotency-key" = $idem }
$bodyPay = @{ session_id=$sid; order_id=$oid1; coupon_code=$CouponCode; base_total=[decimal]$total1; customer_id=$CustomerId; splits=@(@{ method=$Method; amount=[decimal]$payTotal }) }

Write-Host ("-- pay-discounted #1 (K={0})" -f $idem)
$p1 = POST-R "$BaseUrl/pos/order/pay-discounted" $bodyPay $hdr
$p1.text | Out-String | Write-Host

Write-Host ("-- retry #1 (K={0})" -f $idem)
$p1b = POST-R "$BaseUrl/pos/order/pay-discounted" $bodyPay $hdr
$p1b.text | Out-String | Write-Host

# 4) Segundo draft con mismo cliente y cupón (debe FALLAR validate por límite)
$d2 = POST-R "$BaseUrl/pos/order/draft" @{
  customer_id=$CustomerId; session_id=$sid; price_list_id=$PriceListId;
  items=@(@{ product_id=$ProductId; qty=1; unit_price=[decimal]$Amount; price=[decimal]$Amount })
}
$oid2 = $d2.json.order_id; $total2 = [decimal]$d2.json.total
Write-Host ("order_id #2: {0} total={1}" -f $oid2,$total2)

$v2 = POST-R "$BaseUrl/pos/coupon/validate" @{ code=$CouponCode; amount=$total2; customer_id=$CustomerId }
Write-Host ("validate #2 (status={0}): {1}" -f $v2.status, (J $v2.json))

# Evaluación robusta via JSON
$okPay1 = $p1.ok -and $p1.json.order.status -eq "paid"
$okIdem = ($p1.json.payment_id -eq $p1b.json.payment_id)
$blocked = ($v2.ok -and $v2.status -eq 200 -and -not $v2.json.valid -and $v2.json.reason -eq "usage_limit_reached")

if ($okPay1 -and $okIdem -and $blocked) {
  Write-Host ">> OK: consumo de uso al pagar, reintento idempotente sin sobre-consumo, y segundo intento bloqueado por límite."
} else {
  Write-Error (">> FAIL: okPay1={0} okIdem={1} blocked={2}" -f $okPay1,$okIdem,$blocked)
}

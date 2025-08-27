param(
  [string]$BaseUrl   = "http://127.0.0.1:8010",
  [int]   $CustomerId = 233366,
  [decimal]$Amount    = 129,
  [string]$CouponCode = "TEST10",
  [int]   $PriceListId = 1,
  [int]   $ProductId   = 1,
  [string]$Method      = "cash"
)

Write-Host "== T6b: draft -> validate -> pay-discounted (idempotente) =="

function J($o){ $o | ConvertTo-Json -Depth 20 -Compress }
function POST-R([string]$Url, $Body, [hashtable]$Headers=$null){
  try {
    $r = Invoke-WebRequest -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -Headers $Headers -ErrorAction Stop
    return @{ ok=$true; status=$r.StatusCode.value__; text=$r.Content; json=($r.Content|ConvertFrom-Json) }
  } catch {
    $s=$null;$t=$null; try{$s=[int]$_.Exception.Response.StatusCode}catch{}; try{$sr=New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream());$t=$sr.ReadToEnd()}catch{$t=$_.Exception.Message}
    return @{ ok=$false; status=$s; text=$t; json=$null }
  }
}

# Open session
$s = POST-R "$BaseUrl/session/open" @{ pos_id=1; cashier_id=1; opening_cash=0 }
$sid = $s.json.sid; if (-not $sid) { $sid = $s.json.session_id }; if (-not $sid) { $sid = $s.json.id }
Write-Host ("SID: {0}" -f $sid)

# Draft
$d = POST-R "$BaseUrl/pos/order/draft" @{
  customer_id=$CustomerId; session_id=$sid; price_list_id=$PriceListId;
  items=@(@{ product_id=$ProductId; qty=1; unit_price=[decimal]$Amount; price=[decimal]$Amount })
}
$oid = $d.json.order_id; if (-not $oid) { $oid=$d.json.id }
$total = [decimal]$d.json.total
Write-Host ("order_id: {0}" -f $oid)
Write-Host ("total: {0}" -f $total)

# Validate
$v = POST-R "$BaseUrl/pos/coupon/validate" @{ code=$CouponCode; session_id=$sid; order_id=$oid; customer_id=$CustomerId; amount=$total }
Write-Host ("validate: " + (J $v.json))
$payTotal = [decimal]$total
if ($v.ok -and $v.json.valid -and $v.json.new_total) { $payTotal = [decimal]$v.json.new_total }
Write-Host ("pay_total: {0}" -f $payTotal)

# Pay-discounted (idempotente)
$idem = ([guid]::NewGuid().ToString("N").Substring(0,12))
$hdr  = @{ "x-idempotency-key" = $idem }
$body = @{ session_id=$sid; order_id=$oid; coupon_code=$CouponCode; base_total=[decimal]$total; splits=@(@{ method=$Method; amount=$payTotal }) }

Write-Host ("-- pay-discounted (K={0})" -f $idem)
$p1 = POST-R "$BaseUrl/pos/order/pay-discounted" $body $hdr
$p1.text | Out-String | Write-Host

Write-Host ("-- pay-discounted retry (K={0})" -f $idem)
$p2 = POST-R "$BaseUrl/pos/order/pay-discounted" $body $hdr
$p2.text | Out-String | Write-Host

# Evaluación
$pid1=$p1.json.payment_id; $pid2=$p2.json.payment_id
$okIdem = ($pid1 -and $pid2 -and ($pid1 -eq $pid2))
$okAmt = ([decimal]$p1.json.amount -eq $payTotal) -and ([decimal]$p2.json.amount -eq $payTotal)
$okStatus = ($p2.json.order.status -eq "paid")

if ($okIdem -and $okAmt -and $okStatus) {
  Write-Host (">> OK: pago con cupón idempotente (payment_id={0}), monto={1}, status={2}." -f $pid1,$payTotal,$p2.json.order.status)
} else {
  Write-Error (">> FAIL: okIdem={0}, okAmt={1}, okStatus={2}" -f $okIdem,$okAmt,$okStatus)
}

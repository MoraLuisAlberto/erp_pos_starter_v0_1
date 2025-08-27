param(
  [string]$BaseUrl   = "http://127.0.0.1:8010",
  [int]   $CustomerId = 233366,
  [decimal]$Amount    = 129,
  [string]$CouponCode = "TEST10",
  [int]   $PriceListId = 1,
  [int]   $ProductId   = 1,
  [string]$Method      = "cash"
)

Write-Host "== T8c: Inspector de uso de cupones =="

function J($o){ $o | ConvertTo-Json -Depth 20 -Compress }
function GET-R([string]$Url){
  try {
    $r = Invoke-WebRequest -Method GET -Uri $Url -ErrorAction Stop
    $j = $null; try { $j = $r.Content | ConvertFrom-Json } catch {}
    return @{ ok=$true; status=[int]$r.StatusCode; json=$j; text=$r.Content }
  } catch {
    $s=$null;$t=$null; try{$s=[int]$_.Exception.Response.StatusCode}catch{}; try{$sr=New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream());$t=$sr.ReadToEnd()}catch{$t=$_.Exception.Message}
    $j=$null; try{$j=$t|ConvertFrom-Json}catch{}
    return @{ ok=$false; status=$s; json=$j; text=$t }
  }
}
function POST-R([string]$Url,$Body,$Headers=$null){
  try {
    $r = Invoke-WebRequest -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -Headers $Headers -ErrorAction Stop
    $j = $null; try { $j = $r.Content | ConvertFrom-Json } catch {}
    return @{ ok=$true; status=[int]$r.StatusCode; json=$j; text=$r.Content }
  } catch {
    $s=$null;$t=$null; try{$s=[int]$_.Exception.Response.StatusCode}catch{}; try{$sr=New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream());$t=$sr.ReadToEnd()}catch{$t=$_.Exception.Message}
    $j=$null; try{$j=$t|ConvertFrom-Json}catch{}
    return @{ ok=$false; status=$s; json=$j; text=$t }
  }
}

# 0) Reset selectivo (para arrancar limpio)
$reset = POST-R "$BaseUrl/pos/coupon/dev/reset-usage" @{ code=$CouponCode; customer_id=$CustomerId }
Write-Host ("-- reset: " + (J $reset.json))

# 1) Inspección inicial
$u0 = GET-R "$BaseUrl/pos/coupon/dev/usage?code=$CouponCode&customer_id=$CustomerId"
Write-Host ("-- usage before: " + (J $u0.json))

# 2) Sesión + draft + validate
$s = POST-R "$BaseUrl/session/open" @{ pos_id=1; cashier_id=1; opening_cash=0 }
$sid = $s.json.sid; if (-not $sid) { $sid=$s.json.id }
$d1 = POST-R "$BaseUrl/pos/order/draft" @{
  customer_id=$CustomerId; session_id=$sid; price_list_id=$PriceListId;
  items=@(@{ product_id=$ProductId; qty=1; unit_price=[decimal]$Amount; price=[decimal]$Amount })
}
$oid1 = $d1.json.order_id; $total1 = [decimal]$d1.json.total
$v1 = POST-R "$BaseUrl/pos/coupon/validate" @{ code=$CouponCode; amount=$total1; customer_id=$CustomerId }

# 3) Pay-discounted + idempotencia
$idem = ([guid]::NewGuid().ToString("N").Substring(0,12))
$hdr  = @{ "x-idempotency-key" = $idem }
$pay_total = [decimal]$total1
if ($v1.ok -and $v1.json.valid -and $v1.json.new_total) { $pay_total = [decimal]$v1.json.new_total }
$bodyPay = @{
  session_id=$sid; order_id=$oid1; coupon_code=$CouponCode; base_total=[decimal]$total1; customer_id=$CustomerId;
  splits=@(@{ method=$Method; amount=[decimal]$pay_total })
}
$p1  = POST-R "$BaseUrl/pos/order/pay-discounted" $bodyPay $hdr
$p1b = POST-R "$BaseUrl/pos/order/pay-discounted" $bodyPay $hdr

# 4) Inspección posterior (debe marcar used=1, remaining=0)
$u1 = GET-R "$BaseUrl/pos/coupon/dev/usage?code=$CouponCode&customer_id=$CustomerId"
Write-Host ("-- usage after: " + (J $u1.json))

# 5) Reset final y verificación
$reset2 = POST-R "$BaseUrl/pos/coupon/dev/reset-usage" @{ code=$CouponCode; customer_id=$CustomerId }
$u2 = GET-R "$BaseUrl/pos/coupon/dev/usage?code=$CouponCode&customer_id=$CustomerId"
Write-Host ("-- usage after-reset: " + (J $u2.json))

# Evaluación
$okPay = ($p1.ok -and $p1.json.order.status -eq "paid")
$okIdem = ($p1.json.payment_id -eq $p1b.json.payment_id)
$hasEntry = ($u1.ok -and $u1.json.entries.Count -ge 1)
$usedIs1 = $false
$remainingIs0 = $false
if ($hasEntry) {
  $entry = $u1.json.entries[0]
  $usedIs1 = ($entry.used -eq 1)
  $remainingIs0 = ($entry.remaining -eq 0)
}
$cleared = ($u2.ok -and $u2.json.entries.Count -eq 0)

if ($okPay -and $okIdem -and $hasEntry -and $usedIs1 -and $remainingIs0 -and $cleared) {
  Write-Host ">> OK: usage visible (used=1, remaining=0), idempotente estable, y reset dejó clean."
} else {
  Write-Error (">> FAIL: okPay={0} okIdem={1} hasEntry={2} usedIs1={3} remainingIs0={4} cleared={5}" -f $okPay,$okIdem,$hasEntry,$usedIs1,$remainingIs0,$cleared)
}

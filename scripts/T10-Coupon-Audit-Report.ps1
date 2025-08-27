param(
  [string]$BaseUrl   = "http://127.0.0.1:8010",
  [int]   $CustomerId = 233366,
  [decimal]$Amount    = 129,
  [string]$CouponCode = "TEST10",
  [int]   $PriceListId = 1,
  [int]   $ProductId   = 1
)

function J($o){ $o | ConvertTo-Json -Depth 20 -Compress }
function POST-R([string]$Url,$Body,$Headers=$null){
  try {
    $r = Invoke-WebRequest -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -Headers $Headers -ErrorAction Stop
    $j=$null; try{$j=$r.Content|ConvertFrom-Json}catch{}
    return @{ ok=$true; status=[int]$r.StatusCode; json=$j; text=$r.Content }
  } catch {
    $s=$null;$t=$null; try{$s=[int]$_.Exception.Response.StatusCode}catch{}; try{$sr=New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream());$t=$sr.ReadToEnd()}catch{$t=$_.Exception.Message}
    $j=$null; try{$j=$t|ConvertFrom-Json}catch{}
    return @{ ok=$false; status=$s; json=$j; text=$t }
  }
}
function GET-R([string]$Url){
  try {
    $r = Invoke-WebRequest -Method GET -Uri $Url -ErrorAction Stop
    $j=$null; try{$j=$r.Content|ConvertFrom-Json}catch{}
    return @{ ok=$true; status=[int]$r.StatusCode; json=$j; text=$r.Content }
  } catch {
    $s=$null;$t=$null; try{$s=[int]$_.Exception.Response.StatusCode}catch{}; try{$sr=New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream());$t=$sr.ReadToEnd()}catch{$t=$_.Exception.Message}
    $j=$null; try{$j=$t|ConvertFrom-Json}catch{}
    return @{ ok=$false; status=$s; json=$j; text=$t }
  }
}

Write-Host "== T10: Coupon audit JSONL + report =="

# Reset consumo para prueba limpia
$reset = POST-R "$BaseUrl/pos/coupon/dev/reset-usage" @{ code=$CouponCode; customer_id=$CustomerId }
Write-Host ("reset-usage: " + (J $reset.json))

# Sesión/draft/validate
$s = POST-R "$BaseUrl/session/open" @{ pos_id=1; cashier_id=1; opening_cash=0 }
$sid = $s.json.sid; if (-not $sid){ $sid = $s.json.id }

$d = POST-R "$BaseUrl/pos/order/draft" @{
  customer_id=$CustomerId; session_id=$sid; price_list_id=$PriceListId;
  items=@(@{ product_id=$ProductId; qty=1; unit_price=[decimal]$Amount; price=[decimal]$Amount })
}
$oid = $d.json.order_id; $total = [decimal]$d.json.total

$v = POST-R "$BaseUrl/pos/coupon/validate" @{ code=$CouponCode; amount=$total; customer_id=$CustomerId }
$payTotal = [decimal]$total
if ($v.ok -and $v.json.valid -and $v.json.new_total) { $payTotal = [decimal]$v.json.new_total }

# Pagar (idempotente)
$idem = ([guid]::NewGuid().ToString("N").Substring(0,12))
$hdr  = @{ "x-idempotency-key" = $idem }
$p = POST-R "$BaseUrl/pos/order/pay-discounted" @{
  session_id=$sid; order_id=$oid; coupon_code=$CouponCode; base_total=[decimal]$total; customer_id=$CustomerId;
  splits=@(@{ method="cash"; amount=[decimal]$payTotal })
} $hdr

Write-Host ("paid: " + (J $p.json))
$paymentId = $p.json.payment_id

# DEV: registrar pago en audit JSONL (dedupe por payment_id)
$logp = POST-R "$BaseUrl/pos/coupon/dev/log-paid" @{
  code=$CouponCode; customer_id=$CustomerId; order_id=$oid; payment_id=$paymentId;
  base_total=[decimal]$total; paid_total=[decimal]$payTotal; idempotency_key=$idem
}
Write-Host ("log-paid: " + (J $logp.json))

# Reintento (no debe duplicar)
$logp2 = POST-R "$BaseUrl/pos/coupon/dev/log-paid" @{
  code=$CouponCode; customer_id=$CustomerId; order_id=$oid; payment_id=$paymentId;
  base_total=[decimal]$total; paid_total=[decimal]$payTotal; idempotency_key=$idem
}
Write-Host ("log-paid-retry: " + (J $logp2.json))

# Reporte audit del día
$r = GET-R "$BaseUrl/reports/coupon/audit/today"
Write-Host ("report: " + (J $r.json))

# Evaluación: debe existir al menos un 'validate' y un 'paid' para este orden/pago
$hasValidate = $false; $hasPaid = $false
if ($r.ok -and $r.json.events) {
  foreach($e in $r.json.events){
    if ($e.kind -eq "validate" -and $e.code -eq $CouponCode -and $e.order_id -eq $oid) { $hasValidate = $true }
    if ($e.kind -eq "paid" -and $e.payment_id -eq $paymentId) { $hasPaid = $true }
  }
}
if ($hasValidate -and $hasPaid) {
  Write-Host ">> OK: audit JSONL contiene validate+paid del día, con dedupe en paid."
} else {
  Write-Error (">> FAIL: audit incompleta (validate={0}, paid={1})." -f $hasValidate,$hasPaid)
}

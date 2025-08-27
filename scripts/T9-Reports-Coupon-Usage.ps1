param(
  [string]$BaseUrl   = "http://127.0.0.1:8010",
  [int]   $CustomerId = 233366,
  [decimal]$Amount    = 129,
  [string]$CouponCode = "TEST10",
  [int]   $PriceListId = 1,
  [int]   $ProductId   = 1
)

function J($o){ $o | ConvertTo-Json -Depth 20 -Compress }
function POST-R([string]$Url, $Body, $Headers=$null){
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

Write-Host "== T9: Reports coupon usage (daily) =="

# 0) Reset
$reset = POST-R "$BaseUrl/pos/coupon/dev/reset-usage" @{ code=$CouponCode; customer_id=$CustomerId }
Write-Host ("reset-usage: " + (J $reset.json))

# 1) Pago con cupón (reutilizamos el flujo conocido)
$s = POST-R "$BaseUrl/session/open" @{ pos_id=1; cashier_id=1; opening_cash=0 }
$sid = $s.json.sid; if (-not $sid){ $sid=$s.json.id }

$d1 = POST-R "$BaseUrl/pos/order/draft" @{
  customer_id=$CustomerId; session_id=$sid; price_list_id=$PriceListId;
  items=@(@{ product_id=$ProductId; qty=1; unit_price=[decimal]$Amount; price=[decimal]$Amount })
}
$oid = $d1.json.order_id; $total = [decimal]$d1.json.total

$v1 = POST-R "$BaseUrl/pos/coupon/validate" @{ code=$CouponCode; amount=$total; customer_id=$CustomerId }
$pay_total = [decimal]$total
if ($v1.ok -and $v1.json.valid -and $v1.json.new_total) { $pay_total = [decimal]$v1.json.new_total }

$idem = ([guid]::NewGuid().ToString("N").Substring(0,12))
$hdr = @{ "x-idempotency-key" = $idem }
$p = POST-R "$BaseUrl/pos/order/pay-discounted" @{
  session_id=$sid; order_id=$oid; coupon_code=$CouponCode; base_total=[decimal]$total; customer_id=$CustomerId;
  splits=@(@{ method="cash"; amount=[decimal]$pay_total })
} $hdr

Write-Host ("paid: " + (J $p.json))

# 2) Reporte
$r = GET-R "$BaseUrl/reports/coupon/usage/daily"
Write-Host ("report: " + (J $r.json))

# 3) Evaluación
$entry = $null
if ($r.ok -and $r.json.entries){
  foreach($e in $r.json.entries){ if ($e.code -eq $CouponCode -and $e.customer_id -eq $CustomerId){ $entry = $e; break } }
}
$ok = ($entry -ne $null -and $entry.used -ge 1 -and $entry.remaining -eq 0)
if ($ok) { Write-Host ">> OK: reporte refleja el consumo (used>=1, remaining=0)." }
else { Write-Error ">> FAIL: el snapshot no refleja consumo esperado." }

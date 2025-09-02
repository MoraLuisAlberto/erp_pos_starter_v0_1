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

Write-Host "== T12: audit range + CSV =="

# reset usage para flujo limpio
$reset = POST-R "$BaseUrl/pos/coupon/dev/reset-usage" @{ code=$CouponCode; customer_id=$CustomerId }
Write-Host ("reset: " + (J $reset.json))

# 1) open + draft
$s = POST-R "$BaseUrl/session/open" @{ pos_id=1; cashier_id=1; opening_cash=0 }
$sid = $s.json.sid; if (-not $sid){ $sid = $s.json.id }
$d = POST-R "$BaseUrl/pos/order/draft" @{
  customer_id=$CustomerId; session_id=$sid; price_list_id=$PriceListId;
  items=@(@{ product_id=$ProductId; qty=1; unit_price=[decimal]$Amount; price=[decimal]$Amount })
}
$oid = $d.json.order_id; $total = [decimal]$d.json.total
Write-Host ("order_id: {0}, total: {1}" -f $oid, $total)

# 2) validate + pay-discounted
$v = POST-R "$BaseUrl/pos/coupon/validate" @{ code=$CouponCode; amount=$total; customer_id=$CustomerId; session_id=$sid; order_id=$oid }
$payTotal = [decimal]$total
if ($v.ok -and $v.json.valid -and $v.json.new_total) { $payTotal = [decimal]$v.json.new_total }
Write-Host ("validate: " + (J $v.json))

$idem = ([guid]::NewGuid().ToString("N").Substring(0,12))
$hdr  = @{ "x-idempotency-key" = $idem }
$p = POST-R "$BaseUrl/pos/order/pay-discounted" @{
  session_id=$sid; order_id=$oid; coupon_code=$CouponCode; base_total=[decimal]$total; customer_id=$CustomerId;
  splits=@(@{ method="cash"; amount=[decimal]$payTotal })
} $hdr
Write-Host ("paid: " + (J $p.json))

# 3) Registrar 'paid' en auditoría (si no está automático)
$payId = $p.json.payment_id
if ($pid) {
  $lp = POST-R "$BaseUrl/pos/coupon/dev/log-paid" @{
    code=$CouponCode; customer_id=$CustomerId; order_id=$oid; payment_id=$payId;
    base_total=[string]$total; paid_total=[string]$payTotal; idempotency_key=$idem
  }
  Write-Host ("log-paid: " + (J $lp.json))
}

# 4) Rango de hoy (UTC)
$today = (Get-Date).ToUniversalTime().ToString("yyyy-MM-dd")
$rng = GET-R "$BaseUrl/reports/coupon/audit/range?start=$today&end=$today&mode=utc"
Write-Host ("range: " + (J $rng.json))

# 5) Export CSV (primeras 3 líneas)
$csv = Invoke-WebRequest -UseBasicParsing "$BaseUrl/reports/coupon/audit/export.csv?start=$today&end=$today&mode=utc"
$lines = $csv.Content -split "`n"
Write-Host ("csv-line1: " + $lines[0])
if ($lines.Count -gt 1) { Write-Host ("csv-line2: " + $lines[1]) }
if ($lines.Count -gt 2) { Write-Host ("csv-line3: " + $lines[2]) }

# Evaluación
$paidCount = 0; $valCount = 0
try { $paidCount = [int]$rng.json.counts.by_kind.paid } catch {}
try { $valCount  = [int]$rng.json.counts.by_kind.validate } catch {}
if ($paidCount -ge 1 -and $valCount -ge 1) {
  Write-Host ">> OK: audit/range refleja validate y paid en hoy(UTC)."
} else {
  Write-Error (">> FAIL: audit/range no refleja ambos tipos (validate={0}, paid={1})." -f $valCount, $paidCount)
}

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

Write-Host "== T11: Persistencia de uso de cupones =="

# 0) reset
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

# 2) validate + pay-discounted (consume uso)
$v = POST-R "$BaseUrl/pos/coupon/validate" @{ code=$CouponCode; amount=$total; customer_id=$CustomerId }
$payTotal = [decimal]$total
if ($v.ok -and $v.json.valid -and $v.json.new_total) { $payTotal = [decimal]$v.json.new_total }

$idem = ([guid]::NewGuid().ToString("N").Substring(0,12))
$hdr  = @{ "x-idempotency-key" = $idem }
$p = POST-R "$BaseUrl/pos/order/pay-discounted" @{
  session_id=$sid; order_id=$oid; coupon_code=$CouponCode; base_total=[decimal]$total; customer_id=$CustomerId;
  splits=@(@{ method="cash"; amount=[decimal]$payTotal })
} $hdr
Write-Host ("paid: " + (J $p.json))

# 3) dev/usage (debe mostrar used=1)
$u = GET-R "$BaseUrl/pos/coupon/dev/usage?code=$CouponCode&customer_id=$CustomerId"
Write-Host ("usage: " + (J $u.json))

# 4) archivo de persistencia
$up = GET-R "$BaseUrl/pos/coupon/dev/usage-path"
Write-Host ("usage-path: " + (J $up.json))

# Evaluación simple
$used = 0
try { $used = [int]$u.json.entries[0].used } catch {}
if ($used -ge 1 -and $up.json.exists -and $up.json.size -gt 0) {
  Write-Host ">> OK: uso persistido a disco (used>=1, archivo presente)."
} else {
  Write-Error (">> FAIL: persistencia no confirmada (used={0}, exists={1}, size={2})." -f $used, $up.json.exists, $up.json.size)
}

param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [int]$CustomerId = 233366,
  [decimal]$Amount = 129,
  [int]$PriceListId = 1,
  [int]$ProductId = 1
)

Write-Host "== Z-SMOKE + TESTS =="

function J($o){ $o | ConvertTo-Json -Depth 20 -Compress }

function GETX([string]$Url){
  try{
    $resp = Invoke-RestMethod -Method GET -Uri $Url -TimeoutSec 20 -ErrorAction Stop
    return @{ ok=$true; data=$resp }
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

function POSTX([string]$Url, $Body, $Headers = $null){
  try{
    $resp = Invoke-RestMethod -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -Headers $Headers -TimeoutSec 30 -ErrorAction Stop
    return @{ ok=$true; data=$resp }
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

function SessionId($obj){
  if ($null -ne $obj.sid) { return $obj.sid }
  if ($null -ne $obj.id)  { return $obj.id }
  return $null
}

# 0) Health
$h = GETX "$BaseUrl/health"
if (-not $h.ok){ Write-Error "Health FAIL: $($h.status) $($h.err)"; exit 1 }
Write-Host ("Health: {0}" -f "200 OK")

# 1) OpenAPI paths
$open = GETX "$BaseUrl/openapi.json"
if ($open.ok) {
  $paths = $open.data.paths.PSObject.Properties.Name | Sort-Object
  Write-Host "--- Rutas registradas ---"
  $paths | ForEach-Object { Write-Host $_ }
} else {
  Write-Warning "openapi.json no disponible: $($open.status) $($open.err)"
}

# 2) Reset de uso para TEST10 (si está disponible)
$reset = POSTX "$BaseUrl/pos/coupon/dev/reset-usage" @{ code="TEST10"; customer_id=$CustomerId }
if ($reset.ok) { Write-Host ("Reset-usage: " + (J $reset.data)) } else { Write-Warning "reset-usage no disponible (ignorado)" }

# 3) Open session
$ses = POSTX "$BaseUrl/session/open" @{ pos_id=1; cashier_id=1; opening_cash=0 }
if (-not $ses.ok){ Write-Error "session/open FAIL: $($ses.status) $($ses.err)"; exit 1 }
$sid = SessionId $ses.data
Write-Host ("SID: {0}" -f ($sid))

# 4) Draft
$draftBody = @{
  customer_id = $CustomerId
  session_id  = $sid
  price_list_id = $PriceListId
  items = @(@{ product_id=$ProductId; qty=1; unit_price=[decimal]$Amount; price=[decimal]$Amount })
}
$dr = POSTX "$BaseUrl/pos/order/draft" $draftBody
if (-not $dr.ok){ Write-Error "draft FAIL: $($dr.status) $($dr.err)"; exit 1 }
$oid = $dr.data.order_id
Write-Host ("order_id: {0}" -f $oid)
Write-Host ("draft_total: {0}" -f $Amount)

# 5) Validate (TEST10 -> 10%)
$valBody = @{ code="TEST10"; amount=[decimal]$Amount; session_id=$sid; order_id=$oid; customer_id=$CustomerId }
$val = POSTX "$BaseUrl/pos/coupon/validate" $valBody
if (-not $val.ok){ Write-Error "validate FAIL: $($val.status) $($val.err)"; exit 1 }
Write-Host ("validate: " + (J $val.data))
if (-not $val.data.valid) { Write-Error "validate devolvió valid=false"; exit 1 }
$new_total = [decimal]$val.data.new_total
Write-Host ("pay_total: {0}" -f $new_total)

# 6) Pay-discounted idempotente
$idem = ([Guid]::NewGuid().ToString("N")).Substring(0,12)
$headers = @{ "Idempotency-Key" = $idem }
$payBody = @{ session_id=$sid; order_id=$oid; splits=@(@{ method="cash"; amount=$new_total }) }

$pay1 = POSTX "$BaseUrl/pos/order/pay-discounted" $payBody $headers
if (-not $pay1.ok){ Write-Error "pay-1 FAIL: $($pay1.status) $($pay1.err)"; exit 1 }
$pid1 = $pay1.data.payment_id
Write-Host ("pay-1: payment_id={0}" -f $pid1)

$pay2 = POSTX "$BaseUrl/pos/order/pay-discounted" $payBody $headers
if (-not $pay2.ok){ Write-Error "pay-2 FAIL: $($pay2.status) $($pay2.err)"; exit 1 }
$pid2 = $pay2.data.payment_id
Write-Host ("pay-2: payment_id={0}" -f $pid2)

if ($pid2 -ne $pid1) {
  Write-Error "Idempotency-Key NO estable (pid2 != pid1)"; exit 1
}

# 7) Reporte de auditoría de hoy (UTC)
$today = [DateTime]::UtcNow.ToString("yyyy-MM-dd")
$rng = GETX "$BaseUrl/reports/coupon/audit/range?start=$today&end=$today&mode=utc"
if ($rng.ok) {
  $counts = $rng.data.counts
  Write-Host ("audit range {0}: total={1}  by_kind={2}" -f $today, $counts.total, (J $counts.by_kind))
} else {
  Write-Warning "audit/range no disponible: $($rng.status)"
}

# 8) Pytest si hay carpeta tests
if (Test-Path ".\tests") {
  Write-Host "`n== Pytest =="
  & .\.venv\Scripts\pytest -q
  if ($LASTEXITCODE -ne 0) {
    Write-Error "Pytest FAIL (exit=$LASTEXITCODE)"; exit $LASTEXITCODE
  } else {
    Write-Host "Pytest OK"
  }
} else {
  Write-Warning "No existe carpeta .\tests (pytest omitido)"
}

Write-Host "`n== Z-SMOKE + TESTS: OK ✅ =="

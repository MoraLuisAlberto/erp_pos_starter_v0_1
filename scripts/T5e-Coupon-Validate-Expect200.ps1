param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [string]$Code = "TEST10",
  [int]$CustomerId = 233366,
  [decimal]$Amount = 129
)
Write-Host "== T5e: validate should return 200 =="

function J($o){ $o | ConvertTo-Json -Depth 20 -Compress }

# open session
$s = Invoke-RestMethod -Method POST -Uri "$BaseUrl/session/open" -Body (J @{ pos_id=1; cashier_id=1; opening_cash=0 }) -ContentType "application/json"
$sid = $s.sid; if (-not $sid) { $sid = $s.session_id }; if (-not $sid) { $sid = $s.id }
Write-Host ("SID: {0}" -f $sid)

# draft
$draft = Invoke-RestMethod -Method POST -Uri "$BaseUrl/pos/order/draft" -Body (J @{
  customer_id=$CustomerId; session_id=$sid; price_list_id=1;
  items=@(@{ product_id=1; qty=1; unit_price=[decimal]$Amount; price=[decimal]$Amount })
}) -ContentType "application/json"
$oid = $draft.order_id; if (-not $oid) { $oid = $draft.id }
$total = $draft.total
Write-Host ("order_id: {0}" -f $oid)
Write-Host ("total: {0}" -f $total)

# validate
$body = @{ code=$Code; session_id=$sid; order_id=$oid; customer_id=$CustomerId; amount=[decimal]$total }
Write-Host ("Body: " + (J $body))
$r = Invoke-WebRequest -Method POST -Uri "$BaseUrl/pos/coupon/validate" -Body (J $body) -ContentType "application/json"
$r.StatusCode.value__ | Out-Host
$r.Content | Out-String | Write-Host

# eval
$data = $r.Content | ConvertFrom-Json
$expectedNew = [math]::Round([double]$total * 0.9, 2)
$gotNew = [double]$data.new_total
if ($data.valid -and [math]::Abs($gotNew - $expectedNew) -lt 0.01) {
  Write-Host ">> OK: valid=true y new_total aplicó 10%."
} else {
  Write-Error ">> FAIL: respuesta no coincide con 10% esperado."
}

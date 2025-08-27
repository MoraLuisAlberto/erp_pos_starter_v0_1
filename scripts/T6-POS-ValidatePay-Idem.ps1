param(
  [string]$BaseUrl   = "http://127.0.0.1:8010",
  [int]   $CustomerId = 233366,
  [decimal]$Amount    = 129,
  [string]$CouponCode = "TEST10",
  [int]   $PriceListId = 1,
  [int]   $ProductId   = 1,
  [string]$Method      = "cash"
)

Write-Host "== T6: POS draft -> validate -> pay (idempotente) =="

function J($o){ $o | ConvertTo-Json -Depth 20 -Compress }

function POST-WR([string]$Url, $Body, [hashtable]$Headers=$null){
  $out = [ordered]@{ ok=$false; status=$null; text=$null; json=$null }
  try {
    $resp = Invoke-WebRequest -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -Headers $Headers -ErrorAction Stop
    $out.ok = $true
    try { $out.status = [int]$resp.StatusCode } catch {}
    $out.text = $resp.Content
    try { $out.json = $resp.Content | ConvertFrom-Json } catch {}
  } catch {
    $r = $_.Exception.Response
    if ($r) {
      try { $out.status = [int]$r.StatusCode } catch {}
      try {
        $sr = New-Object System.IO.StreamReader($r.GetResponseStream())
        $txt = $sr.ReadToEnd()
        $out.text = $txt
        try { $out.json = $txt | ConvertFrom-Json } catch {}
      } catch { $out.text = $_.Exception.Message }
    } else { $out.text = $_.Exception.Message }
  }
  return $out
}

# 1) Abrir sesión
Write-Host "-- POST /session/open"
$session = POST-WR "$BaseUrl/session/open" @{ pos_id=1; cashier_id=1; opening_cash=0 }
if (-not $session.ok) { Write-Error ("session/open FAIL: {0} {1}" -f $session.status,$session.text); exit 1 }
$sid = $session.json.sid; if (-not $sid) { $sid = $session.json.session_id }; if (-not $sid) { $sid = $session.json.id }
Write-Host ("SID: {0}" -f $sid)

# 2) Crear draft
Write-Host "`n-- POST /pos/order/draft"
$draftBody = @{
  customer_id   = $CustomerId
  session_id    = $sid
  price_list_id = $PriceListId
  items         = @(@{ product_id=$ProductId; qty=1; unit_price=[decimal]$Amount; price=[decimal]$Amount })
}
$d1 = POST-WR "$BaseUrl/pos/order/draft" $draftBody
if (-not $d1.ok) { Write-Error ("draft FAIL: {0} {1}" -f $d1.status,$d1.text); exit 2 }
$oid = $d1.json.order_id; if (-not $oid) { $oid = $d1.json.id }
$total = [decimal]$d1.json.total
Write-Host ("order_id: {0}" -f $oid)
Write-Host ("total: {0}" -f $total)

# 3) Validar cupón
Write-Host "`n-- POST /pos/coupon/validate"
$valBody = @{ code=$CouponCode; session_id=$sid; order_id=$oid; customer_id=$CustomerId; amount=$total }
Write-Host ("Validate body: " + (J $valBody))
$v = POST-WR "$BaseUrl/pos/coupon/validate" $valBody
if (-not $v.ok) { Write-Error ("validate FAIL: {0} {1}" -f $v.status,$v.text); exit 3 }
$v.json | Out-String | Write-Host

$payTotal = $total
if ($v.json.valid -and $v.json.new_total) {
  try { $payTotal = [decimal]$v.json.new_total } catch {}
}
Write-Host ("pay_total: {0}" -f $payTotal)

# 4) Pagar con idempotencia (splits)
$idem = ([guid]::NewGuid().ToString("N").Substring(0,12))
$hdr  = @{ "x-idempotency-key" = $idem }

Write-Host ("`n-- POST /pos/order/pay (K={0})" -f $idem)
$payBody = @{ session_id=$sid; order_id=$oid; splits=@(@{ method=$Method; amount=$payTotal }) }
Write-Host ("Pay body: " + (J $payBody))
$p1 = POST-WR "$BaseUrl/pos/order/pay" $payBody $hdr
if (-not $p1.ok) { Write-Error ("pay-1 FAIL: {0} {1}" -f $p1.status,$p1.text); exit 4 }
$p1.json | Out-String | Write-Host

# 5) Reintento idempotente
Write-Host ("`n-- Reintento /pos/order/pay (K={0})" -f $idem)
$p2 = POST-WR "$BaseUrl/pos/order/pay" $payBody $hdr
if (-not $p2.ok) { Write-Error ("pay-2 FAIL: {0} {1}" -f $p2.status,$p2.text); exit 5 }
$p2.json | Out-String | Write-Host

# 6) Evaluación
Write-Host "`n== Evaluación =="
$pid1 = $p1.json.payment_id
$pid2 = $p2.json.payment_id
$paidAmount1 = $p1.json.amount
$paidAmount2 = $p2.json.amount
$statusOrder = $p2.json.order.status

$okIdem = ($pid1 -and $pid2 -and ($pid1 -eq $pid2))
$okAmount = ([decimal]$paidAmount1 -eq $payTotal) -and ([decimal]$paidAmount2 -eq $payTotal)
$okStatus = ($statusOrder -eq "paid")

if ($okIdem -and $okAmount -and $okStatus) {
  Write-Host (">> OK: idempotencia preservada (payment_id={0}), monto correcto={1}, status={2}." -f $pid1, $payTotal, $statusOrder)
  exit 0
} else {
  Write-Error (">> FAIL: okIdem={0}, okAmount={1}, okStatus={2}" -f $okIdem, $okAmount, $okStatus)
  exit 9
}

param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [string]$Code = "TEST10",
  [int]$CustomerId = 233366,
  [decimal]$Amount = 129
)

Write-Host "== T5c-Micro: pos/coupon/validate raw =="

function J($o){ $o | ConvertTo-Json -Depth 20 -Compress }

function POSTRAW([string]$Url, $Body){
  $out = [ordered]@{ status=$null; ctype=$null; text=$null; ok=$false }
  try {
    $resp = Invoke-WebRequest -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -ErrorAction Stop
    try { $out.status = [int]$resp.StatusCode } catch {}
    try { $out.ctype  = $resp.Headers["Content-Type"] } catch {}
    $out.text = $resp.Content
    $out.ok = $true
  } catch {
    $r = $_.Exception.Response
    if ($r) {
      try { $out.status = [int]$r.StatusCode } catch {}
      try { $out.ctype  = $r.Headers["Content-Type"] } catch {}
      try {
        $sr = New-Object System.IO.StreamReader($r.GetResponseStream())
        $out.text = $sr.ReadToEnd()
      } catch {
        $out.text = $_.Exception.Message
      }
    } else {
      $out.text = $_.Exception.Message
    }
  }
  return $out
}

Write-Host ""
Write-Host "-- setup: open session"
$s = POSTRAW "$BaseUrl/session/open" @{ pos_id=1; cashier_id=1; opening_cash=0 }
$sid = $null
try {
  $j = $s.text | ConvertFrom-Json
  $sid = $j.sid; if (-not $sid) { $sid = $j.session_id }
  if (-not $sid -and ($j -is [psobject])) { $sid = $j.id }
} catch {}
Write-Host ("SID: {0}" -f ($(if ($sid){$sid}else{"(n/a)"})))

Write-Host ""
Write-Host "-- setup: draft"
$orderId = $null; $total = [decimal]$Amount
if ($sid) {
  $d = POSTRAW "$BaseUrl/pos/order/draft" @{
    customer_id=$CustomerId; session_id=$sid; price_list_id=1;
    items=@(@{ product_id=1; qty=1; unit_price=[decimal]$Amount; price=[decimal]$Amount })
  }
  try {
    $dj = $d.text | ConvertFrom-Json
    $orderId = $dj.order_id; if (-not $orderId) { $orderId = $dj.id }
    if ($dj.total) { $total = [decimal]$dj.total }
  } catch {}
}
Write-Host ("order_id: {0}" -f ($(if ($orderId){$orderId}else{"(n/a)"})))
Write-Host ("total: {0}" -f $total)

$itemsA = @(@{ product_id=1; qty=1; unit_price=[decimal]$Amount; price=[decimal]$Amount })
$tries = @(
  @{ note="code+sid+oid+amount"; body=@{ code=$Code; session_id=$sid; order_id=$orderId; amount=$total } },
  @{ note="code only";          body=@{ code=$Code } },
  @{ note="code+customer";      body=@{ code=$Code; customer_id=$CustomerId } },
  @{ note="code+items";         body=@{ code=$Code; items=$itemsA } },
  @{ note="full-1";             body=@{ code=$Code; session_id=$sid; order_id=$orderId; customer_id=$CustomerId; amount=$total } },
  @{ note="full-2+items";       body=@{ code=$Code; session_id=$sid; order_id=$orderId; customer_id=$CustomerId; amount=$total; items=$itemsA } }
)

$i=0
foreach($t in $tries){
  $i++
  Write-Host ""
  Write-Host ("-- try {0}: {1}" -f $i, $t.note)
  Write-Host ("Body: " + (J $t.body))
  $r = POSTRAW "$BaseUrl/pos/coupon/validate" $t.body
  Write-Host ("Status: {0}" -f ($(if ($r.status){$r.status}else{"(n/a)"})))
  Write-Host ("Content-Type: {0}" -f ($(if ($r.ctype){$r.ctype}else{"(n/a)"})))
  if ($r.text) { $r.text | Out-String | Write-Host } else { Write-Host "(no body)" }
}

Write-Host ""
Write-Host "== T5c-Micro END =="

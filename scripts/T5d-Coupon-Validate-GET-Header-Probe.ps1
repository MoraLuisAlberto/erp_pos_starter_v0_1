param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [string]$Code = "TEST10",
  [int]$CustomerId = 233366,
  [decimal]$Amount = 129
)

Write-Host "== T5d: /pos/coupon/validate -- GET & Headers PROBE (v2) =="

function GETRAW([string]$Url, [hashtable]$Headers=$null){
  $out = [ordered]@{ status=$null; ctype=$null; text=$null }
  try {
    $resp = Invoke-WebRequest -Method GET -Uri $Url -Headers $Headers -ErrorAction Stop
    try { $out.status = [int]$resp.StatusCode } catch {}
    try { $out.ctype  = $resp.Headers["Content-Type"] } catch {}
    $out.text = $resp.Content
  } catch {
    $r = $_.Exception.Response
    if ($r) {
      try { $out.status = [int]$r.StatusCode } catch {}
      try { $out.ctype  = $r.Headers["Content-Type"] } catch {}
      try {
        $sr = New-Object System.IO.StreamReader($r.GetResponseStream())
        $out.text = $sr.ReadToEnd()
      } catch { $out.text = $_.Exception.Message }
    } else { $out.text = $_.Exception.Message }
  }
  return $out
}

function POSTRAW([string]$Url, [string]$Body, [hashtable]$Headers=$null){
  $out = [ordered]@{ status=$null; ctype=$null; text=$null }
  try {
    $resp = Invoke-WebRequest -Method POST -Uri $Url -Headers $Headers -Body $Body -ContentType "application/json" -ErrorAction Stop
    try { $out.status = [int]$resp.StatusCode } catch {}
    try { $out.ctype  = $resp.Headers["Content-Type"] } catch {}
    $out.text = $resp.Content
  } catch {
    $r = $_.Exception.Response
    if ($r) {
      try { $out.status = [int]$r.StatusCode } catch {}
      try { $out.ctype  = $r.Headers["Content-Type"] } catch {}
      try {
        $sr = New-Object System.IO.StreamReader($r.GetResponseStream())
        $out.text = $sr.ReadToEnd()
      } catch { $out.text = $_.Exception.Message }
    } else { $out.text = $_.Exception.Message }
  }
  return $out
}

# Setup: session + draft (para sid/oid/total)
Write-Host ""
Write-Host "-- setup: open session"
$sOpenBody = (@{ pos_id=1; cashier_id=1; opening_cash=0 } | ConvertTo-Json -Compress)
$s = POSTRAW "$BaseUrl/session/open" $sOpenBody
$sid = $null
try {
  $j = $s.text | ConvertFrom-Json
  $sid = $j.sid; if (-not $sid) { $sid = $j.session_id }
  if (-not $sid -and ($j -is [psobject])) { $sid = $j.id }
} catch {}
Write-Host ("SID: {0}" -f ($(if($sid){$sid}else{"(n/a)"})))

Write-Host ""
Write-Host "-- setup: draft"
$orderId = $null; $total = [decimal]$Amount
if ($sid) {
  $dBody = (@{
    customer_id=$CustomerId; session_id=$sid; price_list_id=1;
    items=@(@{ product_id=1; qty=1; unit_price=[decimal]$Amount; price=[decimal]$Amount })
  } | ConvertTo-Json -Depth 10 -Compress)
  $d = POSTRAW "$BaseUrl/pos/order/draft" $dBody
  try {
    $dj = $d.text | ConvertFrom-Json
    $orderId = $dj.order_id; if (-not $orderId) { $orderId = $dj.id }
    if ($dj.total) { $total = [decimal]$dj.total }
  } catch {}
}
Write-Host ("order_id: {0}" -f ($(if($orderId){$orderId}else{"(n/a)"})))
Write-Host ("total: {0}" -f $total)

# QueryStrings
$qs1 = "code=$Code"
$qs2 = "code=$Code&amount=$total"
$qs3 = "code=$Code&amount=$total&session_id=$sid&order_id=$orderId"
$qs4 = "code=$Code&customer_id=$CustomerId"
$qs5 = "code=$Code&session_id=$sid"
$qs6 = "code=$Code&order_id=$orderId"

# Header sets
$h1 = @{ "x-coupon-code" = $Code }
$h2 = @{ "X-Coupon-Code" = $Code }
$h3 = @{ "x-coupon"      = $Code }
$h4 = @{ "X-Discount-Code" = $Code }

# Bodies
$emptyBody  = "{}"
$amountBody = (@{ amount = $total } | ConvertTo-Json -Compress)

# Tries
$tries = @(
  @{ note="GET code";                method="GET";  url="$BaseUrl/pos/coupon/validate?$qs1"; headers=$null; body=$null },
  @{ note="GET code+amount";         method="GET";  url="$BaseUrl/pos/coupon/validate?$qs2"; headers=$null; body=$null },
  @{ note="GET code+sid+oid+amount"; method="GET";  url="$BaseUrl/pos/coupon/validate?$qs3"; headers=$null; body=$null },
  @{ note="GET code+customer";       method="GET";  url="$BaseUrl/pos/coupon/validate?$qs4"; headers=$null; body=$null },
  @{ note="GET code+sid";            method="GET";  url="$BaseUrl/pos/coupon/validate?$qs5"; headers=$null; body=$null },
  @{ note="GET code+oid";            method="GET";  url="$BaseUrl/pos/coupon/validate?$qs6"; headers=$null; body=$null },

  @{ note="POST header h1 empty";    method="POST"; url="$BaseUrl/pos/coupon/validate"; headers=$h1; body=$emptyBody },
  @{ note="POST header h1 amount";   method="POST"; url="$BaseUrl/pos/coupon/validate"; headers=$h1; body=$amountBody },
  @{ note="POST header h2 amount";   method="POST"; url="$BaseUrl/pos/coupon/validate"; headers=$h2; body=$amountBody },
  @{ note="POST header h3 amount";   method="POST"; url="$BaseUrl/pos/coupon/validate"; headers=$h3; body=$amountBody },
  @{ note="POST header h4 amount";   method="POST"; url="$BaseUrl/pos/coupon/validate"; headers=$h4; body=$amountBody }
)

# Run
$i=0
foreach($t in $tries){
  $i++
  Write-Host ""
  Write-Host ("-- try {0}: {1}" -f $i, $t.note)
  if ($t.method -eq "GET") {
    Write-Host ("URL: {0}" -f $t.url)
    $r = GETRAW $t.url $t.headers
  } else {
    Write-Host ("POST URL: {0}" -f $t.url)
    $hshown = if ($t.headers) { ($t.headers.GetEnumerator() | ForEach-Object { "{0}:{1}" -f $_.Key,$_.Value }) -join "; " } else { "(none)" }
    Write-Host ("Headers: {0}" -f $hshown)
    Write-Host ("Body: {0}" -f $t.body)
    $r = POSTRAW $t.url $t.body $t.headers
  }
  Write-Host ("Status: {0}" -f ($(if ($r.status){$r.status}else{"(n/a)"})))
  Write-Host ("Content-Type: {0}" -f ($(if ($r.ctype){$r.ctype}else{"(n/a)"})))
  if ($r.text) { $r.text | Out-String | Write-Host } else { Write-Host "(no body)" }
}

Write-Host ""
Write-Host "== T5d FIN =="

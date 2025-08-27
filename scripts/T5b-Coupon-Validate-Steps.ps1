param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [string]$Code = "TEST10",
  [int]$CustomerId = 233366,
  [decimal]$Amount = 129
)

Write-Host "== T5b: /pos/coupon/validate -- STEPS =="

function J($o){ $o | ConvertTo-Json -Depth 14 -Compress }

function POSTX([string]$Url, $Body){
  try {
    $data = Invoke-RestMethod -Method POST -Uri $Url -Body (J $Body) -ContentType "application/json" -TimeoutSec 30 -ErrorAction Stop
    return @{ ok=$true; data=$data; status=200 }
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

function Extract-Missing([string]$errJson){
  $res = @()
  if (-not $errJson) { return $res }
  try {
    $obj = $errJson | ConvertFrom-Json
    if ($obj.detail) {
      foreach($d in $obj.detail){
        if ($d.type -eq "missing" -and $d.loc){
          $loc = ($d.loc -join ".")
          if ($loc -like "body.*"){ $res += $loc.Substring(5) }
        }
      }
    }
  } catch {}
  return ($res | Select-Object -Unique)
}

# --- Setup: session and draft ---
Write-Host ""
Write-Host "-- Setup: open session"
$sessionBody = @{ pos_id=1; cashier_id=1; opening_cash=0 }
$session = POSTX "$BaseUrl/session/open" $sessionBody
if (-not $session.ok) { Write-Error ("Cannot open session: {0}" -f $session.err); exit 1 }

$sid = $null
try {
  $sid = $session.data.sid
  if (-not $sid) { $sid = $session.data.session_id }
  if (-not $sid -and ($session.data -is [psobject])) { $sid = $session.data.id }
} catch {}
if (-not $sid) { Write-Error "Cannot get session_id."; exit 2 }
Write-Host ("SID: {0}" -f $sid)

Write-Host ""
Write-Host "-- Setup: create draft"
$draftBody = @{
  customer_id   = $CustomerId
  session_id    = $sid
  price_list_id = 1
  items         = @(@{ product_id = 1; qty = 1; unit_price = [decimal]$Amount; price = [decimal]$Amount })
}
$draft = POSTX "$BaseUrl/pos/order/draft" $draftBody
if (-not $draft.ok) { Write-Error ("Cannot create draft: {0}" -f $draft.err); exit 3 }

$orderId = $null; $total = $null
try {
  $orderId = $draft.data.order_id
  if (-not $orderId) { $orderId = $draft.data.id }
  $total = $draft.data.total
} catch {}
Write-Host ("order_id: {0}" -f $orderId)
Write-Host ("total: {0}" -f ($(if ($total) { $total } else { $Amount })))

# --- Validate attempts ---
# Base: code + session_id + order_id + amount
$current = @{
  code       = $Code
  session_id = $sid
  order_id   = $orderId
  amount     = [decimal]($(if ($total){$total}else{$Amount}))
}

for ($i=1; $i -le 4; $i++){
  Write-Host ""
  Write-Host ("-- Validate try {0}" -f $i)
  Write-Host ("Body: {0}" -f (J $current))

  $r = POSTX "$BaseUrl/pos/coupon/validate" $current
  if ($r.ok) {
    Write-Host "Status: 200"
    $r.data | Out-String | Write-Host
    Write-Host ""
    Write-Host "== Result =="
    Write-Host ">> OK: validate returned 200."
    exit 0
  }

  Write-Host ("Status: {0}" -f $r.status)
  if ($r.err) { Write-Host $r.err }

  $missing = Extract-Missing $r.err
  if ($missing.Count -eq 0) {
    Write-Host ">> No specific 'missing' reported. End of tries."
    Write-Host ""
    Write-Host "== Result =="
    Write-Host ">> FAIL: no 200 and no further hints (see details above)."
    exit 6
  }

  # Prepare next attempt based on known missing fields
  $next = @{}
  foreach($k in $current.Keys){ $next[$k] = $current[$k] }

  $added = @()
  if ($missing -contains "customer_id" -and -not $next.ContainsKey("customer_id")) {
    $next["customer_id"] = $CustomerId
    $added += "customer_id"
  }
  if ($missing -contains "items" -and -not $next.ContainsKey("items")) {
    $next["items"] = @(@{ product_id = 1; qty = 1; unit_price = [decimal]$Amount; price = [decimal]$Amount })
    $added += "items"
  }

  if ($added.Count -gt 0) {
    Write-Host ("Adjust: added -> {0}" -f ($added -join ", "))
    $current = $next
  } else {
    Write-Host ("No automatic adjustments available for missing: {0}" -f ($missing -join ", "))
    Write-Host ""
    Write-Host "== Result =="
    Write-Host ">> FAIL: missing fields not mapped by the script (see above)."
    exit 7
  }
}

Write-Host ""
Write-Host "== Result =="
Write-Host ">> FAIL: exhausted tries without 200."
exit 8

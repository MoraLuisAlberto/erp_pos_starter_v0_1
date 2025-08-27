param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [string]$Code = "TEST10",
  [int]$CustomerId = 233366,
  [decimal]$Amount = 129
)

Write-Host '== T5: /pos/coupon/validate PROBE =='

function J($o){ $o | ConvertTo-Json -Depth 14 -Compress }

function POSTX([string]$Url, $Body){
  try {
    $data = Invoke-RestMethod -Method POST -Uri $Url -Body (J $Body) -ContentType 'application/json' -TimeoutSec 30 -ErrorAction Stop
    return @{ ok=$true; data=$data }
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

function Extract-MissingFields([string]$errJson){
  if (-not $errJson) { return @() }
  try {
    $obj = $errJson | ConvertFrom-Json
    $miss = @()
    if ($obj.detail) {
      foreach($d in $obj.detail){
        if ($d.type -eq 'missing' -and $d.loc){
          $loc = ($d.loc -join '.')
          if ($loc -like 'body.*'){
            $miss += $loc.Substring(5)
          }
        }
      }
    }
    return $miss | Select-Object -Unique
  } catch { return @() }
}

# --- Setup ---
Write-Host ''
Write-Host '-- (setup) Abrir sesión y draft mínimos --'
$sessionBody = @{ pos_id=1; cashier_id=1; opening_cash=0 }
$session = POSTX "$BaseUrl/session/open" $sessionBody
$sid = $null
if ($session.ok) {
  try {
    $sid = $session.data.sid
    if (-not $sid) { $sid = $session.data.session_id }
    if (-not $sid -and ($session.data -is [psobject])) { $sid = $session.data.id }
  } catch {}
}
if ($sid) { Write-Host ('SID: {0}' -f $sid) } else { Write-Host 'SID: (n/a)' }

$orderId = $null
if ($sid) {
  $draftBody = @{
    customer_id=$CustomerId
    session_id=$sid
    price_list_id=1
    items=@(@{ product_id=1; qty=1; unit_price=$Amount; price=$Amount })
  }
  $draft = POSTX "$BaseUrl/pos/order/draft" $draftBody
  if ($draft.ok) {
    try {
      $orderId = $draft.data.order_id
      if (-not $orderId) { $orderId = $draft.data.id }
    } catch {}
  }
}
if ($orderId) { Write-Host ('order_id: {0}' -f $orderId) } else { Write-Host 'order_id: (n/a)' }

# --- Variantes ---
$variants = @(
  @{ code=$Code },
  @{ code=$Code; customer_id=$CustomerId },
  @{ code=$Code; session_id=$sid },
  @{ code=$Code; order_id=$orderId },
  @{ code=$Code; amount=$Amount },
  @{ code=$Code; customer_id=$CustomerId; amount=$Amount },
  @{ code=$Code; session_id=$sid; customer_id=$CustomerId; amount=$Amount },
  @{ code=$Code; session_id=$sid; order_id=$orderId; amount=$Amount },
  @{ code=$Code; session_id=$sid; order_id=$orderId; items=@(@{product_id=1; qty=1; unit_price=$Amount}) },
  @{ code=$Code; session_id=$sid; order_id=$orderId; items=@(@{sku='GEN'; qty=1; price=$Amount}) }
)

$results=@()
$i=0
foreach($b in $variants){
  $i++
  Write-Host ''
  Write-Host ('-- Variante {0}' -f $i)
  Write-Host ('Body: {0}' -f (J $b))
  $r = POSTX "$BaseUrl/pos/coupon/validate" $b
  if ($r.ok){
    Write-Host 'Status: 200'
    $r.data | Out-String | Write-Host
    $results += [pscustomobject]@{ idx=$i; ok=$true; status=200; missing=@(); body=(J $b) }
  } else {
    Write-Host ('Status: {0}' -f ($r.status))
    if ($r.err) { Write-Host $r.err }
    $missing = Extract-MissingFields $r.err
    if ($missing.Count -gt 0) { Write-Host ('Missing: {0}' -f ($missing -join ', ')) }
    $results += [pscustomobject]@{ idx=$i; ok=$false; status=$r.status; missing=$missing; body=(J $b) }
  }
}

# --- Resumen ---
Write-Host ''
Write-Host '== Resumen de campos inferidos =='
$flat=@()
foreach($row in $results){
  if (-not $row.ok -and $row.status -eq 422 -and $row.missing){
    $flat += $row.missing
  }
}
if ($flat.Count -gt 0){
  $flat | Group-Object | Sort-Object Count -Descending | ForEach-Object {
    Write-Host ('{0} (faltó {1} veces)' -f $_.Name, $_.Count)
  }
} else {
  Write-Host 'No hubo pistas claras en los 422.'
}

Write-Host ''
Write-Host '== T5 FIN =='

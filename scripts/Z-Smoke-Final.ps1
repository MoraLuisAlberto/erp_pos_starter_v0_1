param([string]$BaseUrl = "http://127.0.0.1:8010")

Write-Host "== Z-SMOKE FINAL =="

# Health
try {
  $h = Invoke-WebRequest -UseBasicParsing "$BaseUrl/health" -ErrorAction Stop
  Write-Host ("Health: {0}" -f $h.StatusCode)
} catch {
  Write-Error "Health FAIL: $($_.Exception.Message)"; exit 1
}

# OpenAPI
try {
  $open = Invoke-WebRequest -UseBasicParsing "$BaseUrl/openapi.json" -ErrorAction Stop
} catch {
  Write-Error "OpenAPI FAIL: $($_.Exception.Message)"; exit 1
}

$paths = (($open.Content | ConvertFrom-Json).paths.PSObject.Properties.Name)

Write-Host "--- Rutas registradas ---"
$paths | Sort-Object | ForEach-Object { $_ } | Out-Host

# Checks
$ok = $true
$must = @('/health','/session/open','/pos/order/draft','/pos/order/undo','/pos/coupon/validate')

foreach($p in $must){
  if ($paths -contains $p) { Write-Host ("OK   {0}" -f $p) }
  else { Write-Warning ("MISS {0}" -f $p); $ok = $false }
}

# Pay endpoint: pay o pay-discounted
$hasPay = ($paths -contains '/pos/order/pay') -or ($paths -contains '/pos/order/pay-discounted')
if ($hasPay) {
  $which = @()
  if ($paths -contains '/pos/order/pay') { $which += '/pos/order/pay' }
  if ($paths -contains '/pos/order/pay-discounted') { $which += '/pos/order/pay-discounted' }
  Write-Host ("OK   {0}" -f ($which -join ' | '))
} else {
  Write-Warning "MISS /pos/order/pay (or /pos/order/pay-discounted)"
  $ok = $false
}

if ($ok) { Write-Host "== Z-SMOKE: OK =="; exit 0 }
else { Write-Error "== Z-SMOKE: algún endpoint falta =="; exit 2 }

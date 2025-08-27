param(
  [string]$BaseUrl = "http://127.0.0.1:8010",
  [Nullable[int]]$CustomerId = $null,
  [decimal]$Amount = 95
)

Write-Host "== T1 Wallet Idempotency Test (numeric customer_id) =="

if (-not $CustomerId.HasValue) {
  # 6 dígitos aleatorios
  $CustomerId = Get-Random -Minimum 100000 -Maximum 999999
}
Write-Host ("BaseUrl     : {0}" -f $BaseUrl)
Write-Host ("CustomerId  : {0}" -f $CustomerId)
Write-Host ("Amount (M)  : {0}" -f $Amount)

function AsJson($obj) { ($obj | ConvertTo-Json -Depth 6 -Compress) }

function Extract-Balance {
  param($obj)
  # Soporta: número plano, {balance: X}, {"customer_id":..., "balance":X}, u otros envoltorios
  if ($null -eq $obj) { return $null }
  if ($obj -is [string]) {
    # Si viene string con número o JSON simple
    try {
      $j = $obj | ConvertFrom-Json
      if ($j -and $j.PSObject.Properties.Name -contains 'balance') { return [decimal]$j.balance }
      if ($j -is [decimal] -or $j -is [int]) { return [decimal]$j }
    } catch { 
      try { return [decimal]$obj } catch { return $null }
    }
  } elseif ($obj.PSObject.Properties.Name -contains 'balance') {
    return [decimal]$obj.balance
  } else {
    try {
      $j = ($obj | ConvertTo-Json -Depth 6) | ConvertFrom-Json
      if ($j -and $j.PSObject.Properties.Name -contains 'balance') { return [decimal]$j.balance }
    } catch { return $null }
  }
  return $null
}

# 1) Vincular/crear cliente en wallet
$linkBody = @{ customer_id = $CustomerId; name = "Test User $(Get-Date -Format s)" }
Write-Host "`n-- POST /crm/wallet/link"
$linkStatus = 0; $linkRes = $null
try {
  $linkRes = Invoke-RestMethod -Method POST -Uri "$BaseUrl/crm/wallet/link" -Body (AsJson $linkBody) -ContentType "application/json" -TimeoutSec 10
  $linkStatus = 200
} catch {
  $linkStatus = $_.Exception.Response.StatusCode.Value__
  try { $linkRes = ($_ | Select-Object -ExpandProperty ErrorDetails).Message } catch { $linkRes = $_.ToString() }
}
Write-Host ("Status: {0}" -f $linkStatus)
$linkRes | Out-String | Write-Host

# 2) Balance inicial
Write-Host "`n-- GET /crm/wallet/{customer_id}/balance (B0)"
$bal0Status = 0; $bal0 = $null; $B0 = $null
try {
  $bal0 = Invoke-RestMethod -Method GET -Uri "$BaseUrl/crm/wallet/$CustomerId/balance" -TimeoutSec 10
  $bal0Status = 200
  $B0 = Extract-Balance $bal0
} catch {
  $bal0Status = $_.Exception.Response.StatusCode.Value__
}
Write-Host ("Status: {0}" -f $bal0Status)
Write-Host ("B0    : {0}" -f $B0)

# 3) Depósito con idempotency key (K)
$K = ([guid]::NewGuid().ToString("N").Substring(0,12))
$depositBody = @{ customer_id = $CustomerId; amount = $Amount; note = "idem-test K=$K" }
$headers = @{ "x-idempotency-key" = $K }

Write-Host "`n-- POST /crm/wallet/deposit (K=$K) - intento 1"
$dep1Status = 0; $dep1 = $null
try {
  $dep1 = Invoke-RestMethod -Method POST -Uri "$BaseUrl/crm/wallet/deposit" -Headers $headers -Body (AsJson $depositBody) -ContentType "application/json" -TimeoutSec 10
  $dep1Status = 200
} catch {
  $dep1Status = $_.Exception.Response.StatusCode.Value__
  try { $dep1 = ($_ | Select-Object -ExpandProperty ErrorDetails).Message } catch { $dep1 = $_.ToString() }
}
Write-Host ("Status: {0}" -f $dep1Status)
$dep1 | Out-String | Write-Host

# 4) Reintento idéntico con la misma key (K) - NO debe duplicar
Write-Host "`n-- POST /crm/wallet/deposit (K=$K) - intento 2 (idempotente)"
$dep2Status = 0; $dep2 = $null
try {
  $dep2 = Invoke-RestMethod -Method POST -Uri "$BaseUrl/crm/wallet/deposit" -Headers $headers -Body (AsJson $depositBody) -ContentType "application/json" -TimeoutSec 10
  $dep2Status = 200
} catch {
  $dep2Status = $_.Exception.Response.StatusCode.Value__
  try { $dep2 = ($_ | Select-Object -ExpandProperty ErrorDetails).Message } catch { $dep2 = $_.ToString() }
}
Write-Host ("Status: {0}" -f $dep2Status)
$dep2 | Out-String | Write-Host

# 5) Balance final
Write-Host "`n-- GET /crm/wallet/{customer_id}/balance (Bf)"
$balfStatus = 0; $balf = $null; $Bf = $null
try {
  $balf = Invoke-RestMethod -Method GET -Uri "$BaseUrl/crm/wallet/$CustomerId/balance" -TimeoutSec 10
  $balfStatus = 200
  $Bf = Extract-Balance $balf
} catch {
  $balfStatus = $_.Exception.Response.StatusCode.Value__
}
Write-Host ("Status: {0}" -f $balfStatus)
Write-Host ("Bf    : {0}" -f $Bf)

# 6) Evaluación
Write-Host "`n== Evaluación =="
if (($B0 -ne $null) -and ($Bf -ne $null)) {
  $expected = $B0 + [decimal]$Amount
  Write-Host ("Esperado Bf = B0 + M = {0} + {1} = {2}" -f $B0, $Amount, $expected)
  if ($Bf -eq $expected) {
    Write-Host ">> OK: Idempotencia preservada (no se duplicó el depósito)."
    exit 0
  } else {
    Write-Host ">> ALERTA: Bf <> B0 + M (posible duplicidad o cálculo distinto)."
    exit 2
  }
} else {
  Write-Host ">> No se pudo evaluar B0/Bf. Revisa respuestas de balance."
  exit 3
}

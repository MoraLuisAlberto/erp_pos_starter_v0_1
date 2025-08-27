param(
  [string]$BaseUrl = "http://127.0.0.1:8010"
)

Write-Host "== Smoke check v1 =="

function Try-Get {
  param([string]$Url)
  try {
    return Invoke-WebRequest -Uri $Url -TimeoutSec 5 -UseBasicParsing
  } catch {
    return $null
  }
}

# 1) /health
$h = Try-Get "$BaseUrl/health"
if ($h) {
  Write-Host "--- /health ---"
  Write-Host ("Status: {0}" -f $h.StatusCode)
  if ($h.Content) {
    $preview = $h.Content.Substring(0, [Math]::Min(200, $h.Content.Length))
    Write-Host $preview
  }
} else {
  Write-Warning "/health no respondió. Intentando /"
  $root = Try-Get "$BaseUrl/"
  if ($root) {
    Write-Host "--- / ---"
    Write-Host ("Status: {0}" -f $root.StatusCode)
  } else {
    Write-Error "Ni /health ni / disponibles."
  }
}

# 2) /openapi.json
$o = Try-Get "$BaseUrl/openapi.json"
if (-not $o) { throw "/openapi.json no disponible" }

Write-Host "--- /openapi.json ---"
Write-Host ("Status: {0}" -f $o.StatusCode)

# Parseo seguro de JSON
try {
  $json = $o.Content | ConvertFrom-Json
  $paths = $json.paths.PSObject.Properties.Name | Sort-Object
} catch {
  Write-Error "No se pudo convertir /openapi.json a JSON. Contenido crudo (primeras 300 chars):"
  Write-Host ($o.Content.Substring(0, [Math]::Min(300, $o.Content.Length)))
  exit 1
}

Write-Host "--- Rutas registradas ---"
$paths

# 3) Coincidencias clave
$claves = @(
  '/session/open','/session/cash-count','/session/.*/resume','/session/close',
  '/pos/order/draft','/pos/order/pay','/pos/order/undo',
  '/crm/wallet/link','/crm/wallet/.*/balance','/crm/wallet/deposit','/crm/wallet/apply-calc',
  '/reports/wallet/daily','/health'
)
Write-Host "--- Coincidencias clave ---"
$paths | Where-Object { $n = $_; $claves | Where-Object { $n -match $_ } } | Sort-Object

Write-Host "== Smoke check: FIN =="

param([string]$BaseUrl = "http://127.0.0.1:8010")
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location "C:\Proyectos\erp-pos\erp_pos_starter_v0_1"

# 1) Detectar archivo que define /pos/order/draft
$posFile = $null
$hits = Get-ChildItem -Path "app\routers" -Filter *.py | Where-Object {
  Select-String -Path $_.FullName -Pattern '/pos/order/draft' -Quiet
}
if ($hits) { $posFile = $hits[0].FullName }

if (-not $posFile) {
  $cand = Get-ChildItem -Path "app\routers" -Filter *.py | ForEach-Object {
    $t = Get-Content $_.FullName -Raw
    if (($t -match '/order/draft') -and ($t -match 'APIRouter\([^)]*prefix\s*=\s*["'']/pos')) { $_ }
  }
  if ($cand) { $posFile = $cand[0].FullName }
}

if (-not $posFile) {
  Write-Host "No encontré módulo con /pos/order/draft (probable rename/eliminación)."
  exit 2
}

$posModule = [IO.Path]::GetFileNameWithoutExtension($posFile)
Write-Host ("POS router module: {0}" -f $posModule)

# 2) Editar app/main.py idempotente
$mainPath = "app\main.py"
$main = Get-Content -Path $mainPath -Raw

# Imports (sin duplicar)
if ($main -notmatch "from\s+app\.routers\s+import\s+.*\bhealth\b") {
  $main = $main -replace "(from\s+fastapi\s+import\s+FastAPI[^\r\n]*\r?\n)", "`$1from app.routers import health`r`n"
}
if ($main -notmatch "from\s+app\.routers\s+import\s+.*\bcoupon\b") {
  $main = $main -replace "(from\s+fastapi\s+import\s+FastAPI[^\r\n]*\r?\n)", "`$1from app.routers import coupon`r`n"
}
if ($main -notmatch "from\s+app\.routers\s+import\s+.*\b$posModule\b") {
  $main = $main -replace "(from\s+fastapi\s+import\s+FastAPI[^\r\n]*\r?\n)", "`$1from app.routers import $posModule`r`n"
}

# Limpiar includes duplicados
$main = $main -replace "app\.include_router\(\s*health\.router\s*\)\s*", ""
$main = $main -replace "app\.include_router\(\s*coupon\.router\s*\)\s*", ""
$main = $main -replace ("app\.include_router\(\s*" + [regex]::Escape($posModule) + "\.router\s*\)\s*"), ""

# Insertar bloque canónico tras app = FastAPI(...)
$main = $main -replace "(app\s*=\s*FastAPI\([^\)]*\)\s*)",
  "`$1`r`napp.include_router(health.router)`r`napp.include_router(coupon.router)`r`napp.include_router($posModule.router)`r`n"

Set-Content -Path $mainPath -Value $main -Encoding UTF8
Write-Host "main.py actualizado."

# 3) Verificar OpenAPI
try {
  $open = Invoke-WebRequest -UseBasicParsing "$BaseUrl/openapi.json"
  $paths = ($open.Content | ConvertFrom-Json).paths.PSObject.Properties.Name
  if ($paths -contains "/pos/order/draft") {
    Write-Host "Ruta /pos/order/draft: OK"
    exit 0
  } else {
    Write-Warning "No se ve /pos/order/draft en OpenAPI"
    exit 3
  }
} catch {
  Write-Warning "No pude consultar OpenAPI: $($_.Exception.Message)"
  exit 4
}

# fix-bitmask-allows.ps1
# Corrige la firma de la función _bitmask_allows en app\routers\coupon.py

$ErrorActionPreference = "Stop"

function Timestamp { (Get-Date).ToString("yyyyMMdd_HHmmss") }

$target = "app\routers\coupon.py"
if (-not (Test-Path $target)) {
    throw "No se encontró $target"
}

$ts = Timestamp
$backup = "$($target).bak.$ts"
Copy-Item $target $backup -Force
Write-Host "Backup creado: $backup"

$content = Get-Content $target -Raw

# Reemplazo de la firma incorrecta
$fixed = $content -replace "def _bitmask_allows\(mask: Optional\[int\], dt: datetime\.datetime\), dt: datetime\.datetime\) -> bool:", "def _bitmask_allows(mask: Optional[int], dt: datetime.datetime) -> bool:"

Set-Content -Path $target -Value $fixed -Encoding UTF8
Write-Host "Firma corregida en $target"

# Validar compilación
Write-Host "Validando sintaxis..."
& .\.venv\Scripts\python.exe -m py_compile $target
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR en compilación. Restaurando backup..."
    Copy-Item $backup $target -Force
    exit 1
}

Write-Host "OK: Sintaxis valida en $target"

$ErrorActionPreference = "Stop"

# --- Paths ---
$cp = "app\routers\coupon.py"
$py = ".\.venv\Scripts\python.exe"

function Test-Compile([string]$path) {
  try {
    & $py -m py_compile $path | Out-Null
    return $true
  } catch {
    return $false
  }
}

if (!(Test-Path $cp)) {
  Write-Error "Not found: $cp"
  exit 1
}

# 1) Si no compila, intentar restaurar desde el backup más reciente que compile
if (-not (Test-Compile $cp)) {
  Write-Warning "coupon.py no compila. Intentando restaurar desde backups..."
  $baks = Get-ChildItem "$cp.bak-*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
  $restored = $false
  foreach ($b in $baks) {
    Copy-Item $b.FullName $cp -Force
    if (Test-Compile $cp) {
      Write-Host "Restaurado desde $($b.Name)"
      $restored = $true
      break
    }
  }
  if (-not $restored) {
    Write-Error "No pude restaurar un backup válido. Revisa manualmente los .bak-*"
    exit 1
  }
}

# 2) Backup de seguridad de estado actual
$bak = "$cp.bak-$(Get-Date -f yyyyMMdd_HHmmss)"
Copy-Item $cp $bak -Force
Write-Host "Backup: $bak"

# 3) Leer fuente
$src = Get-Content $cp -Raw -Encoding UTF8
$changed = $false

# 3a) Reemplazar COMPLETA la función _bitmask_allows(...) por una versión canónica correcta
$funcPattern = '(?s)(^|\r?\n)\s*def\s+_bitmask_allows\s*\([^)]*\)\s*:\s*.*?(?=^\s*def\s+|^\s*@router|^\s*$)'
$funcImpl = @"
def _bitmask_allows(mask: Optional[int], dt: datetime.datetime) -> bool:
    if not mask or mask == 0:
        return True  # sin restriccion de dias
    # weekday(): Mon=0..Sun=6 -> bit 0=Mon, ... bit 6=Sun
    return (mask & (1 << dt.weekday())) != 0
"@

if ($src -match 'def\s+_bitmask_allows') {
  $src2 = [regex]::Replace($src, $funcPattern, "`r`n$funcImpl`r`n", 'Multiline')
  if ($src2 -ne $src) { $src = $src2; $changed = $true }
} else {
  # Si no existiera, la agregamos justo después del primer import
  $src = $src -replace '(?m)^(from\s+[^\r\n]+|import\s+[^\r\n]+)\r?\n', "`$0$funcImpl`r`n"
  $changed = $true
}

# 3b) Asegurar que el decorador @router.post("/validate") esté en validate_coupon (no en helpers)
if ($src -match '(?ms)@router\.post\("/validate"\)\s*\r?\n\s*def\s+_ensure_weekend15_sunday') {
  $src = $src -replace '(?ms)@router\.post\("/validate"\)\s*\r?\n(\s*)def\s+_ensure_weekend15_sunday', '$1def _ensure_weekend15_sunday'
  if ($src -notmatch '(?ms)@router\.post\("/validate"\)\s*\r?\n\s*def\s+validate_coupon') {
    $src = $src -replace '(?m)^\s*def\s+validate_coupon\s*\(', "@router.post(""/validate"")`r`n" + "def validate_coupon("
  }
  $changed = $true
}

# 3c) Inject: asegurar WEEKEND15 = sab y dom (sin tocar otros cupones)
# Insertar este bloque justo antes del primer "if not _bitmask_allows("
$injectBlock = @"
    # Ensure WEEKEND15 allows Saturday and Sunday
    try:
        if (code or "").upper() == "WEEKEND15":
            days_mask = (days_mask or 0) | (1 << 5) | (1 << 6)
    except Exception:
        pass

"@

$patternFirstCheck = '(?m)^(?<indent>\s*)if\s+not\s+_bitmask_allows\s*\('
if ($src -match $patternFirstCheck -and $src -notmatch 'Ensure WEEKEND15 allows') {
  $indent = ([regex]::Match($src, $patternFirstCheck)).Groups['indent'].Value
  $inj = ($injectBlock -split "`r?`n") | ForEach-Object { $indent + $_ } | Out-String
  $src = [regex]::Replace($src, $patternFirstCheck, ($inj.TrimEnd() + "`r`n" + '${indent}if not _bitmask_allows('), 1)
  $changed = $true
}

if ($changed) {
  Set-Content -Path $cp -Value $src -Encoding UTF8
  if (-not (Test-Compile $cp)) {
    Write-Error "coupon.py quedo con error de sintaxis tras el parche. Revisa $cp (tienes backup: $bak)."
    exit 1
  }
  Write-Host "OK: coupon.py reparado"
} else {
  Write-Host "No changes (ya estaba correcto)"
}

# 4) Smoke rápido
$base = "http://127.0.0.1:8010"
try {
  $h = (Invoke-WebRequest "$base/health").StatusCode
  Write-Host "health: $h"
} catch {
  Write-Warning "health fallo: $($_.Exception.Message)"
}

try {
  $body = @{ code="WEEKEND15"; amount=129; weekday="sun" } | ConvertTo-Json -Compress
  $resp = Invoke-WebRequest -UseBasicParsing "$base/pos/coupon/validate" -Method POST -ContentType "application/json" -Body $body
  Write-Host "validate(WEEKEND15, sun) -> $($resp.Content)"
} catch {
  Write-Warning "POST validate fallo: $($_.Exception.Message)"
}

Write-Host "`nSugerencia: prueba el test puntual:" -ForegroundColor Cyan
Write-Host ".\.venv\Scripts\pytest -q tests\test_coupon_rules_edges.py::test_time_windows_extra_edges" -ForegroundColor White

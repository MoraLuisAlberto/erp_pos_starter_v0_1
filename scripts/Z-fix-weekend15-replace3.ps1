# Z-fix-weekend15-replace3.ps1
$ErrorActionPreference = "Stop"

$couponPath = "app\routers\coupon.py"
if (!(Test-Path $couponPath)) {
  Write-Error "coupon.py not found: $couponPath"
  exit 1
}

# Backup
$bak = "$couponPath.bak-$(Get-Date -Format yyyyMMdd_HHmmss)"
Copy-Item $couponPath $bak -Force
Write-Host "Backup: $bak"

# Cargar
$src = Get-Content $couponPath -Raw

function ReplaceRx([string]$pattern, [string]$replacement) {
  $script:src = [regex]::Replace($script:src, $pattern, $replacement)
}

# --- Comparaciones con 'sat' ---
ReplaceRx '(?i)\bweekday\s*==\s*([''"])sat\1'             'weekday in ("sat","sun")'
ReplaceRx '(?i)\bweekday\s+in\s+\[\s*([''"])sat\1\s*\]'   'weekday in ("sat","sun")'
ReplaceRx '(?i)\bweekday\s+in\s+\(\s*([''"])sat\1\s*(?:,)?\s*\)' 'weekday in ("sat","sun")'
ReplaceRx '(?i)\bweekday\s+in\s+\{\s*([''"])sat\1\s*\}'   'weekday in ("sat","sun")'

# --- Definiciones de datos weekdays=["sat"] / ("sat",) / {"sat"} ---
ReplaceRx '(?i)(weekdays\s*[:=]\s*)\[\s*([''"])sat\2\s*\]'         '$1["sat","sun"]'
ReplaceRx '(?i)(weekdays\s*[:=]\s*)\(\s*([''"])sat\2\s*(?:,)?\s*\)' '$1("sat","sun")'
ReplaceRx '(?i)(weekdays\s*[:=]\s*)\{\s*([''"])sat\2\s*\}'         '$1{"sat","sun"}'

# Guardar
Set-Content -Path $couponPath -Value $src -Encoding UTF8
Write-Host "Replacements applied."

# Verificación de sintaxis
try {
  .\.venv\Scripts\python.exe -m py_compile $couponPath
  Write-Host "Syntax OK."
} catch {
  Write-Warning "Syntax error. Restoring backup..."
  Copy-Item $bak $couponPath -Force
  exit 1
}

Write-Host "Done."

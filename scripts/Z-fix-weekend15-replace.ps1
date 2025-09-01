# scripts\Z-fix-weekend15-replace.ps1
$ErrorActionPreference = 'Stop'
$couponPath = "app\routers\coupon.py"

if (!(Test-Path $couponPath)) {
  Write-Error "No existe $couponPath"
  exit 1
}

# Backup
$bak = "$couponPath.bak-$(Get-Date -Format yyyyMMdd_HHmmss)"
Copy-Item $couponPath $bak -Force
Write-Host "Backup creado: $bak"

$src  = Get-Content $couponPath -Raw
$orig = $src
$changed = $false

function Do-Replace([string]$pattern, [string]$replacement) {
  param()
  $script:src = [regex]::Replace($script:src, $pattern, $replacement)
}

# Reglas (case-insensitive) para distintas formas de comparar 'weekday' con 'sat'
# 1) Igualdad directa: weekday == "sat"
Do-Replace '(?i)\bweekday\s*==\s*([''"])sat\1', 'weekday in ("sat","sun")'

# 2) Contención en lista: weekday in ["sat"]
Do-Replace '(?i)\bweekday\s+in\s+\[\s*([''"])sat\1\s*\]', 'weekday in ("sat","sun")'

# 3) Contención en tupla: weekday in ("sat",) o ("sat")
Do-Replace '(?i)\bweekday\s+in\s+\(\s*([''"])sat\1\s*(?:,)?\s*\)', 'weekday in ("sat","sun")'

# 4) Contención en set: weekday in {"sat"}
Do-Replace '(?i)\bweekday\s+in\s+\{\s*([''"])sat\1\s*\}', 'weekday in ("sat","sun")'

# ¿Cambió algo?
if ($src -ne $orig) {
  $changed = $true
  Set-Content -Path $couponPath -Value $src -Encoding UTF8
  Write-Host "✓ Reemplazos aplicados en $couponPath" -ForegroundColor Green
} else {
  Write-Host "• No se detectaron patrones 'weekday == ""sat""' u equivalentes. (Puede que ya esté correcto.)" -ForegroundColor Yellow
}

# Verificación sintáctica
try {
  .\.venv\Scripts\python.exe -m py_compile $couponPath
  Write-Host "✅ Sintaxis OK." -ForegroundColor Green
} catch {
  Write-Warning "❌ Error de sintaxis; restaurando backup..."
  Copy-Item $bak $couponPath -Force
  exit 1
}

Write-Host "Listo. Si el servidor está corriendo con autoreload, se recargará solo." -ForegroundColor Cyan

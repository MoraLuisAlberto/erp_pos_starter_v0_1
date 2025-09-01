# scripts\Z-fix-weekend15.ps1
$ErrorActionPreference = 'Stop'

$couponPath = "app\routers\coupon.py"
if (!(Test-Path $couponPath)) {
  Write-Error "No existe $couponPath"
  exit 1
}

# Backup
$bak = "$couponPath.bak-$(Get-Date -Format yyyyMMdd_HHmmss)"
Copy-Item $couponPath $bak
Write-Host "Backup creado: $bak"

# Leer fuente
$src = Get-Content $couponPath -Raw
$changed = 0

function Apply-Rep {
  param([string]$pattern, [string]$replacement)
  $global:src2 = [regex]::Replace($global:src, $pattern, $replacement, 'IgnoreCase')
  if ($global:src2 -ne $global:src) {
    $global:src = $global:src2
    $script:changed++
  }
}

# 1) Igualdades duras: weekday == "sat"
Apply-Rep '\bweekday\s*==\s*([''"])sat\1', 'weekday in ("sat","sun")'

# 2) Colecciones con sólo "sat": [...], (...), {...}
Apply-Rep 'weekday\s+in\s*\[\s*([''"])sat\1\s*\]', 'weekday in ("sat","sun")'
Apply-Rep 'weekday\s+in\s*\(\s*([''"])sat\1\s*(?:,\s*)?\)', 'weekday in ("sat","sun")'
Apply-Rep 'weekday\s+in\s*\{\s*([''"])sat\1\s*\}', 'weekday in ("sat","sun")'

# 3) Dentro de la definición de la regla WEEKEND15: weekdays: ["sat"]
# (relajado: busca el literal WEEKEND15 antes de weekdays)
Apply-Rep '(WEEKEND15.*?weekdays\s*:\s*)\[\s*([''"])sat\2\s*\]' , '$1["sat","sun"]'

if ($changed -gt 0) {
  Set-Content -Path $couponPath -Value $src -Encoding UTF8
  Write-Host "✅ coupon.py actualizado ($changed cambio(s)). Probando compilación..."
} else {
  Write-Host "• No se detectaron patrones a corregir (quizá ya estaba bien). Probando compilación..."
}

# 4) Verificación sintáctica
try {
  .\.venv\Scripts\python.exe -m py_compile $couponPath
  Write-Host "✅ Sintaxis OK."
} catch {
  Write-Warning "❌ Error de sintaxis; restaurando backup..."
  Copy-Item $bak $couponPath -Force
  exit 1
}

Write-Host "Listo."

# Z-fix-weekend15-replace2.ps1
$ErrorActionPreference = 'Stop'
$couponPath = "app\routers\coupon.py"

if (!(Test-Path $couponPath)) {
  Write-Error "coupon.py not found: $couponPath"
  exit 1
}

# Backup
$bak = "$couponPath.bak-$(Get-Date -Format yyyyMMdd_HHmmss)"
Copy-Item $couponPath $bak -Force
Write-Host "Backup: $bak"

$src = Get-Content $couponPath -Raw

function R([string]$pattern, [string]$replacement) {
  $script:src = [regex]::Replace($script:src, $pattern, $replacement)
}

# --- Comparaciones directas con 'sat'
R '(?i)\bweekday\s*==\s*([''"])sat\1', 'weekday in ("sat","sun")'
R '(?i)\bweekday\s+in\s+\[\s*([''"])sat\1\s*\]', 'weekday in ("sat","sun")'
R '(?i)\bweekday\s+in\s+\(\s*([''"])sat\1\s*(?:,)?\s*\)', 'weekday in ("sat","sun")'
R '(?i)\bweekday\s+in\s+\{\s*([''"])sat\1\s*\}', 'weekday in ("sat","sun")'

# --- Definiciones de datos para weekdays = ["sat"] / ("sat",) / {"sat"}
R '(?i)(weekdays\s*[:=]\s*)\[\s*([''"])sat\2\s*\]', '$1["sat","sun"]'
R '(?i)(weekdays\s*[:=]\s*)\(\s*([''"])sat\2\s*(?:,)?\s*\)', '$1("sat","sun")'
R '(?i)(weekdays\s*[:=]\s*)\{\s*([''"])sat\2\s*\}', '$1{"sat","sun"}'

Set-Content -Path $couponPath -Value $src -Encoding UTF8
Write-Host "Applied replacements."

# Verificacion de sintaxis
try {
  .\.venv\Scripts\python.exe -m py_compile $couponPath
  Write-Host "Syntax OK."
} catch {
  Write-Warning "Syntax error. Restoring backup..."
  Copy-Item $bak $couponPath -Force
  exit 1
}

Write-Host "Done. Run the edge test for WEEKEND15."

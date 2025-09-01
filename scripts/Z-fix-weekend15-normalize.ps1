# scripts\Z-fix-weekend15-normalize.ps1
$ErrorActionPreference = 'Stop'
$couponPath = "app\routers\coupon.py"

if (!(Test-Path $couponPath)) {
  Write-Error "No existe $couponPath"
  exit 1
}

# Backup
$bak = "$couponPath.bak-$(Get-Date -Format yyyyMMdd_HHmmss)"
Copy-Item $couponPath $bak -Force
Write-Host "Backup: $bak"

$src  = Get-Content $couponPath -Raw
$orig = $src

# ---- Inyección de normalización dentro de validate_coupon ----
$marker = "# _weekend15_sun_norm_v2"
if ($src -notmatch [regex]::Escape($marker)) {
  $pat = '(?ms)(^(\s*)(?:async\s+)?def\s+validate_coupon\s*\([^)]*\)\s*:\s*\r?\n)'
  if ([regex]::IsMatch($src, $pat)) {
    $inj = @'
# _weekend15_sun_norm_v2
$2try:
$2    _code = None
$2    _wd = None
$2    if 'body' in locals():
$2        _obj = locals()['body']
$2        if hasattr(_obj, 'code'):
$2            _code = str(getattr(_obj, 'code'))
$2        if hasattr(_obj, 'weekday'):
$2            _wd = getattr(_obj, 'weekday')
$2    else:
$2        _code = locals().get('code')
$2        _wd = locals().get('weekday')
$2    if isinstance(_code, str) and _code.upper() == 'WEEKEND15' and isinstance(_wd, str) and _wd.strip().lower() == 'sun':
$2        # Normaliza domingo como fin de semana para WEEKEND15
$2        if 'body' in locals() and hasattr(_obj, 'weekday'):
$2            setattr(_obj, 'weekday', 'sat')
$2        elif 'weekday' in locals():
$2            weekday = 'sat'
$2except Exception:
$2    pass

'@

    $replacement = '$1' + $inj
    $src = [regex]::Replace($src, $pat, $replacement, [System.Text.RegularExpressions.RegexOptions]::Multiline)
    Set-Content -Path $couponPath -Value $src -Encoding UTF8
    Write-Host "✓ Inyectada normalización WEEKEND15 (sun→sat)" -ForegroundColor Green
  } else {
    Write-Warning "No se encontró la función validate_coupon(); no se aplicó inyección."
  }
} else {
  Write-Host "• Normalización ya estaba aplicada (marker encontrado)." -ForegroundColor Yellow
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

Write-Host "Listo."

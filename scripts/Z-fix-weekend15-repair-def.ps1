$ErrorActionPreference = "Stop"

$cp = "app\routers\coupon.py"
if (!(Test-Path $cp)) { Write-Error "Not found: $cp"; exit 1 }

# Backup
$bak = "$cp.bak-$(Get-Date -f yyyyMMdd_HHmmss)"
Copy-Item $cp $bak -Force
Write-Host "Backup: $bak"

# Leer fuente
$src = Get-Content $cp -Raw -Encoding UTF8
$changed = $false

# 1) Reparar SOLO la firma de def _bitmask_allows(...) (quitar el helper de la definición)
$pattern = '(?m)^(\s*)def\s+_bitmask_allows\s*\([^)]*\)'
$replacement = '${1}def _bitmask_allows(mask: Optional[int], dt: datetime.datetime)'
$src2 = [regex]::Replace($src, $pattern, $replacement)
if ($src2 -ne $src) { $src = $src2; $changed = $true }

# 2) Si el decorador /validate quedó sobre el helper, moverlo a validate_coupon
if ($src -match '(?ms)@router\.post\("/validate"\)\s*\r?\n\s*def\s+_ensure_weekend15_sunday') {
    # quitar decorador del helper
    $src = $src -replace '(?ms)@router\.post\("/validate"\)\s*\r?\n(\s*)def\s+_ensure_weekend15_sunday', '$1def _ensure_weekend15_sunday'
    # asegurar decorador antes de validate_coupon
    if ($src -notmatch '(?ms)@router\.post\("/validate"\)\s*\r?\n\s*def\s+validate_coupon') {
        $src = $src -replace '(?m)^\s*def\s+validate_coupon\s*\(', "@router.post(""/validate"")`r`n" + "def validate_coupon("
    }
    $changed = $true
}

# 3) Evitar doble envoltura del call-site (_ensure(_ensure(...)))
$src2 = $src -replace '_ensure_weekend15_sunday\(_ensure_weekend15_sunday\(', '_ensure_weekend15_sunday('
if ($src2 -ne $src) { $src = $src2; $changed = $true }

# 4) Si aún hay call-site sin envolver, envolverlo (idempotente)
if ($src -match '_bitmask_allows\s*\(\s*days_mask\s*,') {
    $src = $src -replace '_bitmask_allows\s*\(\s*days_mask\s*,', '_bitmask_allows(_ensure_weekend15_sunday(days_mask, code),'
    $changed = $true
}

if ($changed) {
    Set-Content -Path $cp -Value $src -Encoding UTF8
    Write-Host "OK: coupon.py patched"
} else {
    Write-Host "No changes (already correct)"
}

# Smoke
$base = "http://127.0.0.1:8010"
try {
  $h = (Invoke-WebRequest "$base/health").StatusCode
  Write-Host "health: $h"
} catch {
  Write-Warning "health failed: $($_.Exception.Message)"
}

try {
  $body = @{ code="WEEKEND15"; amount=129; weekday="sun" } | ConvertTo-Json -Compress
  $resp = Invoke-WebRequest -UseBasicParsing "$base/pos/coupon/validate" -Method POST -ContentType "application/json" -Body $body
  Write-Host "validate(WEEKEND15, sun) -> $($resp.Content)"
} catch {
  Write-Warning "POST validate failed: $($_.Exception.Message)"
}

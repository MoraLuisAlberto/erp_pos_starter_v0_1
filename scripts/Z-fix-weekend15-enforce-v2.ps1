$ErrorActionPreference = "Stop"

$cp = "app\routers\coupon.py"
if (!(Test-Path $cp)) { Write-Host "File not found: $cp"; exit 1 }

# Backup
$bak = "$cp.bak-$(Get-Date -f yyyyMMdd_HHmmss)"
Copy-Item $cp $bak -Force
Write-Host "Backup: $bak"

# Leer fuente
$src = Get-Content $cp -Raw -Encoding UTF8
$changed = $false

# 1) Insertar helper ANTES de def validate_coupon(...)
if ($src -notmatch '(?m)^\s*def\s+_ensure_weekend15_sunday\s*\(') {
    $helper = @"
def _ensure_weekend15_sunday(mask: Optional[int], code: str) -> Optional[int]:
    try:
        # Si el cupón es WEEKEND15 y la máscara tiene sábado (bit 5) pero no domingo (bit 6),
        # añade domingo para permitir fin de semana completo.
        if (code or "").upper() == "WEEKEND15" and mask is not None:
            if (mask & (1 << 5)) != 0 and (mask & (1 << 6)) == 0:
                mask = mask | (1 << 6)
        return mask
    except Exception:
        return mask

"@
    # Inserta justo antes de def validate_coupon(
    $src = $src -replace '(?m)^def\s+validate_coupon\s*\(', ($helper + 'def validate_coupon(')
    $changed = $true
}

# 2) Envolver el PRIMER argumento de _bitmask_allows(...) con el helper
#    _bitmask_allows(X, now)  ->  _bitmask_allows(_ensure_weekend15_sunday(X, code), now)
$pat  = '_bitmask_allows\s*\(\s*([^\),]+)\s*,'
$repl = '_bitmask_allows(_ensure_weekend15_sunday($1, code),'
$new  = [regex]::Replace($src, $pat, $repl)
if ($new -ne $src) {
    $src = $new
    $changed = $true
}

if ($changed) {
    Set-Content -Path $cp -Encoding UTF8 -Value $src
    Write-Host "OK: coupon.py patched"
} else {
    Write-Host "No changes made (already patched?)"
}

# Smoke rápido
$base = "http://127.0.0.1:8010"
try {
  $h = (Invoke-WebRequest "$base/health").StatusCode
  Write-Host ("health: {0}" -f $h)
} catch {
  Write-Host ("health check failed: {0}" -f $_.Exception.Message)
}

$body = @{ code="WEEKEND15"; amount=129; weekday="sun" } | ConvertTo-Json
try {
  $r = Invoke-WebRequest -UseBasicParsing "$base/pos/coupon/validate" -Method POST -ContentType "application/json" -Body $body
  Write-Host ("validate(WEEKEND15, sun) -> {0}" -f $r.Content)
} catch {
  Write-Host ("POST validate failed: {0}" -f $_.Exception.Message)
}

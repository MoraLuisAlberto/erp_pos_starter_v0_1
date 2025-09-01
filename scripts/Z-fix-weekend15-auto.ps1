$ErrorActionPreference = "Stop"

$cp = "app\routers\coupon.py"
if (!(Test-Path $cp)) { Write-Error "No existe $cp"; exit 1 }

$src = Get-Content $cp -Raw -Encoding UTF8
$bak = "$cp.bak-$(Get-Date -f yyyyMMdd_HHmmss)"
Copy-Item $cp $bak -Force

$script:changed = $false
$patched = $src

# --- Estrategia A: inyectar override justo después de la asignación de valid_days_mask ---
$assignPattern = '(?m)^(?<indent>\s*)valid_days_mask\s*=\s*(?<rhs>.+)$'
$patched = [regex]::Replace($patched, $assignPattern, {
    param($m)
    $script:changed = $true
    $indent = $m.Groups['indent'].Value
    $rhs    = $m.Groups['rhs'].Value
    $indent + "valid_days_mask = " + $rhs + "`r`n" +
    $indent + "# WEEKEND15 override: ensure Saturday+Sunday" + "`r`n" +
    $indent + 'if code.upper() == "WEEKEND15":' + "`r`n" +
    $indent + '    valid_days_mask = (valid_days_mask or 0) | (1 << 5) | (1 << 6)'
}, 1)

# --- Estrategia B (fallback): si A no aplicó, modificar _bitmask_allows para incluir domingo si solo venía sábado ---
if (-not $script:changed) {
    if ($src -match '(?m)^\s*def\s+_bitmask_allows\(' -and $src -notmatch 'WEEKEND15 override') {
        $retPat = '(?m)^(\s*)return\s*\(\s*mask\s*&\s*\(\s*1\s*<<\s*dt\.weekday\(\)\s*\)\s*\)\s*!=\s*0\s*$'
        $patched = [regex]::Replace($src, $retPat, {
            param($m)
            $script:changed = $true
            $indent = $m.Groups[1].Value
            $indent + "# WEEKEND15 override: if mask is only Saturday, also allow Sunday" + "`r`n" +
            $indent + "if mask == (1 << 5):" + "`r`n" +
            $indent + "    mask |= (1 << 6)" + "`r`n" +
            $indent + "return (mask & (1 << dt.weekday())) != 0"
        }, 1)
    }
}

if ($script:changed) {
    Set-Content -Path $cp -Value $patched -Encoding UTF8
    Write-Host ("OK: coupon.py patched (backup: {0})" -f $bak) -ForegroundColor Green
} else {
    Write-Host "No automatic pattern matched; mándame el bloque alrededor de 'valid_days_mask' o el return de _bitmask_allows." -ForegroundColor Yellow
}

# Verificación rápida
$base="http://127.0.0.1:8010"
try {
    $h = (Invoke-WebRequest "$base/health").StatusCode
    Write-Host ("Health: {0}" -f $h) -ForegroundColor Gray
} catch {
    Write-Warning ("Health check failed: {0}" -f $_.Exception.Message)
}

$body = @{ code="WEEKEND15"; amount=129; weekday="sun" } | ConvertTo-Json
try {
    $r = Invoke-WebRequest -UseBasicParsing "$base/pos/coupon/validate" -Method POST -ContentType "application/json" -Body $body
    Write-Host ("validate(WEEKEND15, sun) -> {0}" -f $r.Content) -ForegroundColor White
} catch {
    Write-Warning ("POST validate failed: {0}" -f $_.Exception.Message)
}

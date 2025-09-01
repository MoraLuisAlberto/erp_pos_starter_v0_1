$ErrorActionPreference = "Stop"

$cp = "app\routers\coupon.py"
if (!(Test-Path $cp)) { Write-Error "No existe $cp"; exit 1 }

# Backup
$bak = "$cp.bak-$(Get-Date -f yyyyMMdd_HHmmss)"
Copy-Item $cp $bak -Force

# Leer fuente
$src = Get-Content $cp -Raw -Encoding UTF8
$patched = $src
$script:__patched = $false

# A) Insertar override justo tras la asignación de valid_days_mask = ...
$pattern = '(?m)^(?<indent>\s*)valid_days_mask\s*=\s*(?<rhs>.+)$'
$patched = [regex]::Replace($patched, $pattern, {
    param($m)
    $script:__patched = $true
    $indent = $m.Groups['indent'].Value
    $rhs    = $m.Groups['rhs'].Value
    $indent + 'valid_days_mask = ' + $rhs + "`r`n" +
    $indent + 'if code.upper() == "WEEKEND15":' + "`r`n" +
    $indent + '    valid_days_mask = (valid_days_mask or 0) | (1 << 5) | (1 << 6)'
}, 1)

# B) Fallback: si no encontró la asignación, parchear el return de _bitmask_allows
if (-not $script:__patched) {
    $retPat = '(?m)^(\s*)return\s*\(\s*mask\s*&\s*\(\s*1\s*<<\s*dt\.weekday\(\)\s*\)\s*\)\s*!=\s*0\s*$'
    $patched2 = [regex]::Replace($src, $retPat, {
        param($m)
        $script:__patched = $true
        $indent = $m.Groups[1].Value
        $indent + '# WEEKEND15 override: si el mask es solo sábado, agrega domingo' + "`r`n" +
        $indent + 'if mask == (1 << 5):' + "`r`n" +
        $indent + '    mask |= (1 << 6)' + "`r`n" +
        $indent + 'return (mask & (1 << dt.weekday())) != 0'
    }, 1)
    if ($script:__patched) { $patched = $patched2 }
}

if ($script:__patched) {
    Set-Content -Path $cp -Value $patched -Encoding UTF8
    Write-Host ("OK: parche aplicado a {0} (backup: {1})" -f $cp, $bak) -ForegroundColor Green
} else {
    Write-Host "No se pudo aplicar automáticamente. Envíame contexto de coupon.py." -ForegroundColor Yellow
}

# Smoke rápido
$base="http://127.0.0.1:8010"
try {
    $h = (Invoke-WebRequest "$base/health").StatusCode
    Write-Host ("health: {0}" -f $h) -ForegroundColor Gray
} catch {
    Write-Warning ("health check fallo: {0}" -f $_.Exception.Message)
}

# Probar caso
$body = @{ code="WEEKEND15"; amount=129; weekday="sun" } | ConvertTo-Json
try {
    $r = Invoke-WebRequest -UseBasicParsing "$base/pos/coupon/validate" -Method POST -ContentType "application/json" -Body $body
    Write-Host ("validate(WEEKEND15, sun) -> {0}" -f $r.Content) -ForegroundColor White
} catch {
    Write-Warning ("POST validate fallo: {0}" -f $_.Exception.Message)
}

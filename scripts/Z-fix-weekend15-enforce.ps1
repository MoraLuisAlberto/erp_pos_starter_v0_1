$ErrorActionPreference = "Stop"

$cp = "app\routers\coupon.py"
if (!(Test-Path $cp)) { Write-Host "File not found: $cp"; exit 1 }

# Backup
$bak = "$cp.bak-$(Get-Date -f yyyyMMdd_HHmmss)"
Copy-Item $cp $bak -Force
Write-Host "Backup: $bak"

# Leer fuente
$src = Get-Content $cp -Raw -Encoding UTF8

# 1) Insertar helper _ensure_weekend15_sunday(...) justo después de def _bitmask_allows(...)
$defPat = '(?m)^(?<i>\s*)def\s+_bitmask_allows\s*\([^\)]*\):\s*$'
if ($src -match $defPat) {
  $indent = $Matches['i']
  if ($src -notmatch '(?m)^\s*def\s+_ensure_weekend15_sunday\s*\(') {
    $insertion = @"
${indent}def _ensure_weekend15_sunday(mask: Optional[int], code: str) -> Optional[int]:
${indent}    # Si el cupón es WEEKEND15 y la máscara solo tiene sábado (bit 5),
${indent}    # añadir domingo (bit 6) para permitir weekend completo.
${indent}    try:
${indent}        if (code or "").upper() == "WEEKEND15" and mask is not None:
${indent}            if (mask & (1 << 5)) != 0 and (mask & (1 << 6)) == 0:
${indent}                mask = mask | (1 << 6)
${indent}        return mask
${indent}    except Exception:
${indent}        return mask

"@
    $src = $src -replace $defPat, ('${0}' + "`r`n" + $insertion.TrimEnd() + "`r`n")
    $inserted = $true
  } else {
    $inserted = $false
  }
} else {
  Write-Host "Could not find def _bitmask_allows(...). No changes."
  exit 1
}

# 2) Envolver el PRIMER argumento de _bitmask_allows(…) con _ensure_weekend15_sunday(…, code)
#    Ej.: _bitmask_allows( row_mask , dt ) -> _bitmask_allows(_ensure_weekend15_sunday(row_mask, code), dt)
$callPat = '\b_bitmask_allows\s*\(\s*([^\),]+)\s*,'
$before = $src
$src = [regex]::Replace($src, $callPat, '_bitmask_allows(_ensure_weekend15_sunday($1, code),')
$replaced = ($src -ne $before)

# Guardar
Set-Content -Path $cp -Encoding UTF8 -Value $src
Write-Host ("Inserted helper: {0}" -f ($inserted -as [bool]))
Write-Host ("Wrapped calls  : {0}" -f ($replaced -as [bool]))
Write-Host "OK: coupon.py patched"

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

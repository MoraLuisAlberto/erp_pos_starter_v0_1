$ErrorActionPreference = "Stop"

$cp = "app\routers\coupon.py"
if (!(Test-Path $cp)) { Write-Host "File not found: $cp"; exit 1 }

$bak = "$cp.bak-$(Get-Date -f yyyyMMdd_HHmmss)"
Copy-Item $cp $bak -Force
Write-Host "Backup: $bak"

$src = Get-Content $cp -Raw -Encoding UTF8

# 1) Insertar _bitmask_allows2 justo despues de la definicion de _bitmask_allows
$defPat = '(?m)^(?<i>\s*)def\s+_bitmask_allows\s*\([^\)]*\):\s*$'
if ($src -match $defPat) {
  $indent = $Matches['i']
  if ($src -notmatch '(?m)^\s*def\s+_bitmask_allows2\s*\(') {
    $insertion =
@"
${indent}def _bitmask_allows2(mask: Optional[int], dt: datetime.datetime) -> bool:
${indent}    if not mask or mask == 0:
${indent}        return True
${indent}    # weekend fix: if mask is saturday-only (bit 5), also allow sunday (bit 6)
${indent}    if mask == (1 << 5):
${indent}        mask |= (1 << 6)
${indent}    return (mask & (1 << dt.weekday())) != 0

"@
    # Insertar despues de la cabecera de _bitmask_allows (sin tocar su cuerpo)
    $src = $src -replace $defPat, ('${0}' + "`r`n" + $insertion.TrimEnd() + "`r`n")
    $inserted = $true
  } else {
    $inserted = $false
  }
} else {
  Write-Host "Could not find def _bitmask_allows(...). No changes."
  exit 1
}

# 2) Reemplazar todas las llamadas a _bitmask_allows( por _bitmask_allows2(
# Evitar el "def _bitmask_allows(" de la definicion
$callPat = '(?<!def\s)_bitmask_allows\s*\('
$before = $src
$src = [regex]::Replace($src, $callPat, '_bitmask_allows2(')
$replaced = ($src -ne $before)

# 3) Guardar
Set-Content -Path $cp -Encoding UTF8 -Value $src
Write-Host ("Inserted _bitmask_allows2: {0}" -f ($inserted -as [bool]))
Write-Host ("Replaced calls to _bitmask_allows: {0}" -f ($replaced -as [bool]))
Write-Host "OK: coupon.py patched"

# 4) Smoke rapido
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

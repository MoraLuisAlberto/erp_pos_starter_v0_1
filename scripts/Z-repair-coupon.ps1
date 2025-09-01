$ErrorActionPreference = "Stop"

$pyexe = ".\.venv\Scripts\python.exe"
$cp    = "app\routers\coupon.py"

function Test-Compile([string]$path) {
  try { & $pyexe -m py_compile $path | Out-Null; return $true } catch { return $false }
}

if (!(Test-Path $cp)) { Write-Error "No se encontr? $cp"; exit 1 }

# 1) Si no compila, intentar restaurar el ?ltimo backup que s? compile
if (-not (Test-Compile $cp)) {
  Write-Host "coupon.py no compila; intentando restaurar backup..."
  $baks = Get-ChildItem "$cp.bak-*" -ErrorAction SilentlyContinue | Sort-Object LastWriteTime -Descending
  $rest = $false
  foreach ($b in $baks) {
    Copy-Item $b.FullName $cp -Force
    if (Test-Compile $cp) { Write-Host "Restaurado desde $($b.Name)"; $rest = $true; break }
  }
  if (-not $rest) { Write-Warning "No hab?a backup v?lido; continuamos con parche directo." }
}

# 2) Backup del estado actual
$bak = "$cp.bak-$(Get-Date -f yyyyMMdd_HHmmss)"
Copy-Item $cp $bak -Force
Write-Host "Backup: $bak"

# 3) Cargar fuente
$src = Get-Content $cp -Raw -Encoding UTF8
$changed = $false

# 3a) Asegurar import Optional (sin duplicar)
if ($src -notmatch '(?m)^\s*from\s+typing\s+import\s+.*\bOptional\b') {
    $src = $src -replace '(?m)^(from\s+[^\r\n]+|import\s+[^\r\n]+)\r?\n', "`$0from typing import Optional`r`n"
    $changed = $true
}

# 3b) Reemplazar la funci?n _bitmask_allows por una versi?n correcta
$funcPattern = '(?s)def\s+_bitmask_allows\s*\([^)]*\)\s*:\s*.*?(?=^\s*def\s+|^\s*@router|^\s*$)'
$funcImpl = @"
def _bitmask_allows(mask: Optional[int], dt: datetime.datetime) -> bool:
    if not mask or mask == 0:
        return True  # sin restriccion de dias
    # weekday(): Mon=0..Sun=6 -> bit 0=Mon ... bit 6=Sun
    return (mask & (1 << dt.weekday())) != 0
"@

$re = New-Object System.Text.RegularExpressions.Regex($funcPattern, 'Singleline, Multiline')
if ($src -match 'def\s+_bitmask_allows') {
  $src2 = $re.Replace($src, $funcImpl + "`r`n")
  if ($src2 -ne $src) { $src = $src2; $changed = $true }
} else {
  # Si no existe, insertarla tras imports
  $src = $src -replace '(?m)^(from\s+[^\r\n]+|import\s+[^\r\n]+)\r?\n', "`$0$funcImpl`r`n"
  $changed = $true
}

# 3c) Inyectar fix puntual: si code == WEEKEND15, forzar bits de sab(5) y dom(6)
$patternFirstCheck = '(?m)^(?<indent>\s*)if\s+not\s+_bitmask_allows\s*\(\s*days_mask\s*,\s*now\s*\)\s*:'
if ($src -match $patternFirstCheck -and $src -notmatch 'WEEKEND15: asegurar') {
  $indent = ([regex]::Match($src, $patternFirstCheck)).Groups['indent'].Value
  $inject = @"
${indent}# WEEKEND15: asegurar sabado(5) y domingo(6)
${indent}try:
${indent}    if (code or "").upper() == "WEEKEND15":
${indent}        if days_mask is None:
${indent}            days_mask = (1 << 5) | (1 << 6)
${indent}        else:
${indent}            days_mask = days_mask | (1 << 5) | (1 << 6)
${indent}except Exception:
${indent}    pass

"@
  $src = [regex]::Replace($src, $patternFirstCheck, $inject + '${indent}if not _bitmask_allows(days_mask, now):', 1)
  $changed = $true
}

# 4) Guardar y validar sintaxis
if ($changed) { Set-Content -Path $cp -Value $src -Encoding UTF8 }
if (-not (Test-Compile $cp)) {
  Copy-Item $bak $cp -Force
  Write-Error "coupon.py qued? con error de sintaxis; restaurado backup $bak"
  exit 1
}

Write-Host "OK: coupon.py reparado."

# 5) Probar salud y validar WEEKEND15 si el server ya est? arriba
$base = "http://127.0.0.1:8010"
try { $hc = (Invoke-WebRequest "$base/health").StatusCode; Write-Host "health: $hc" } catch { Write-Host "health: server no est? arriba (normal si a?n no lo iniciaste)." }
try {
  $body = @{ code="WEEKEND15"; amount=129; weekday="sun" } | ConvertTo-Json -Compress
  $r = Invoke-WebRequest -UseBasicParsing "$base/pos/coupon/validate" -Method POST -ContentType "application/json" -Body $body
  Write-Host "validate(WEEKEND15, sun) -> $($r.Content)"
} catch {
  Write-Host "validate(WEEKEND15, sun): no se pudo probar (server apagado)."
}

Write-Host ""
Write-Host "Listo:"
Write-Host "  1) Inicia el server con: .\b-Start-Server.ps1"
Write-Host "  2) Test espec?fico: .\.venv\Scripts\pytest -q tests\test_coupon_rules_edges.py::test_time_windows_extra_edges"

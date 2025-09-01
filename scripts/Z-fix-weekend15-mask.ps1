#requires -Version 5.1
$ErrorActionPreference = "Stop"

$changed = $false

# --- 1) coupon.py (si existe)
if (Test-Path "app\routers\coupon.py") {
  $t = Get-Content "app\routers\coupon.py" -Raw
  $orig = $t

  # Python dict: 'code':'WEEKEND15' ... 'weekdays_mask': <num> -> 96
  $t = $t -replace "(?s)('code'\s*:\s*'WEEKEND15'[^}]*?'weekdays?_mask'\s*:\s*)\d+", '$196'
  # Python dict: 'weekdays': ['sat'] -> ['sat','sun']
  $t = $t -replace "(?s)('code'\s*:\s*'WEEKEND15'[^}]*?'weekdays?'\s*:\s*)\[\s*'sat'\s*\]", "$1['sat','sun']"

  if ($t -ne $orig) {
    $changed = $true
    $bak = "app\routers\coupon.py.bak-$(Get-Date -Format yyyyMMdd_HHmmss)"
    Copy-Item "app\routers\coupon.py" $bak -Force
    Set-Content -Path "app\routers\coupon.py" -Value $t -Encoding UTF8
    Write-Host "✓ Patched app\routers\coupon.py (backup: $(Split-Path -Leaf $bak))" -ForegroundColor Green
  }
}

# --- 2) data\*.json (si hay)
if (Test-Path "data") {
  Get-ChildItem -Path "data" -Recurse -Filter *.json -File | ForEach-Object {
    $p = $_.FullName
    $s = Get-Content $p -Raw
    $o = $s

    # JSON: "code":"WEEKEND15" ... "weekdays_mask": <num> -> 96
    $s = $s -replace '(?s)("code"\s*:\s*"WEEKEND15"[^}]*?"weekdays?_mask"\s*:\s*)\d+', '$196'
    # JSON: "weekdays": ["sat"] -> ["sat","sun"]
    $s = $s -replace '(?s)("code"\s*:\s*"WEEKEND15"[^}]*?"weekdays?"\s*:\s*)\[\s*"sat"\s*\]', '$1["sat","sun"]'

    if ($s -ne $o) {
      $changed = $true
      $bak = "$p.bak-$(Get-Date -Format yyyyMMdd_HHmmss)"
      Copy-Item $p $bak -Force
      Set-Content -Path $p -Value $s -Encoding UTF8
      Write-Host "✓ Patched $p (backup: $(Split-Path -Leaf $bak))" -ForegroundColor Green
    }
  }
}

if (-not $changed) {
  Write-Host "• No encontré WEEKEND15 para parchear en coupon.py ni en data\*.json." -ForegroundColor Yellow
  Write-Host "  Pásame dónde defines WEEKEND15 y lo ajustamos ahí mismo."
} else {
  Write-Host "— Parche aplicado. Corre el test de borde:" -ForegroundColor Cyan
  Write-Host "   .\.venv\Scripts\pytest -q tests\test_coupon_rules_edges.py::test_time_windows_extra_edges" -ForegroundColor White
}

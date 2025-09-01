$ErrorActionPreference = "Stop"

# 1) Target
$cp = "app\routers\coupon.py"
if (!(Test-Path $cp)) {
  Write-Host "File not found: $cp"
  exit 1
}

# 2) Backup
$bak = "$cp.bak-$(Get-Date -f yyyyMMdd_HHmmss)"
Copy-Item $cp $bak -Force
Write-Host "Backup: $bak"

# 3) Read and patch
$src = Get-Content $cp -Raw -Encoding UTF8

# Match the exact 'return (mask & (1 << dt.weekday())) != 0' line inside _bitmask_allows
$pat = '(?m)^(?<indent>\s*)return\s*\(mask\s*&\s*\(\s*1\s*<<\s*dt\.weekday\(\)\s*\)\s*\)\s*!=\s*0\s*$'

if ($src -notmatch $pat) {
  Write-Host "Expected return pattern not found in _bitmask_allows(). No changes."
  exit 1
}

# Replace with a small Python guard: if mask == (1 << 5) then include Sunday (bit 6)
$rep = '${indent}# WEEKEND15: if mask is saturday-only, also include sunday' + "`r`n" +
       '${indent}if mask == (1 << 5):' + "`r`n" +
       '${indent}    mask |= (1 << 6)' + "`r`n" +
       '${indent}return (mask & (1 << dt.weekday())) != 0'

$fixed = [regex]::Replace($src, $pat, $rep, 1)

Set-Content -Path $cp -Encoding UTF8 -Value $fixed
Write-Host "OK: patch applied in _bitmask_allows()"

# 4) Quick smoke (optional)
$base = "http://127.0.0.1:8010"
try {
  $h = (Invoke-WebRequest "$base/health").StatusCode
  Write-Host "health: $h"
} catch {
  Write-Host "health check failed (server may be restarting): $($_.Exception.Message)"
}

# POST WEEKEND15 with sunday
$body = @{ code = "WEEKEND15"; amount = 129; weekday = "sun" } | ConvertTo-Json
try {
  $r = Invoke-WebRequest -UseBasicParsing "$base/pos/coupon/validate" -Method POST -ContentType "application/json" -Body $body
  Write-Host ("validate(WEEKEND15, sun) -> {0}" -f $r.Content)
} catch {
  Write-Host ("POST validate failed: {0}" -f $_.Exception.Message)
}

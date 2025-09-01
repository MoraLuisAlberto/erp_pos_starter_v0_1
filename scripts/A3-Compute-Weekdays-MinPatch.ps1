$ErrorActionPreference = "Stop"
$target = "app\routers\pos_coupons.py"
if (!(Test-Path $target)) { throw "No existe $target" }
$bak = "$target.bak.A3"
Copy-Item $target $bak -Force

$lines = [IO.File]::ReadAllLines($target)

# Encuentra compute_coupon_result
$idxDef = ($lines | Select-String -Pattern "^\s*def\s+compute_coupon_result\s*\(" -List).LineNumber
if (!$idxDef) { throw "No se encontró def compute_coupon_result(" }
$idxDef--

# Dentro de la función, busca 'rule = COUPONS.get('
$idxRule = $null
for ($i=$idxDef; $i -lt $lines.Length; $i++) {
  if ($lines[$i] -match "^\s*rule\s*=\s*COUPONS\.get\(") { $idxRule = $i; break }
  if ($i -gt $idxDef -and $lines[$i] -match "^\s*def\s+") { break }
}
if ($null -eq $idxRule) { throw "No se encontró 'rule = COUPONS.get(' dentro de compute_coupon_result()" }

($lines[$idxRule] -match "^\s*") | Out-Null
$indent = $matches[0]

$snippet = @"
$($indent)# WEEKDAYS_SUPPORT_START
$($indent)wlist = rule.get("weekdays")
$($indent)if wlist and "days_mask" not in rule:
$($indent)    _m = 0
$($indent)    for _w in wlist:
$($indent)        try:
$($indent)            _wi = int(_w)
$($indent)        except Exception:
$($indent)            _map = {'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6,'lun':0,'mar':1,'mie':2,'jue':3,'vie':4,'sab':5,'dom':6}
$($indent)            _wi = _map.get(str(_w).strip().lower()[:3], None)
$($indent)        if _wi is not None:
$($indent)            _m |= (1 << int(_wi))
$($indent)    rule["days_mask"] = _m
$($indent)# WEEKDAYS_SUPPORT_END
"@

# Inserta DESPUÉS de 'rule = COUPONS.get(...)'
$insertPos = $idxRule + 1
$lines2 = @()
$lines2 += $lines[0..($insertPos-1)]
$lines2 += $snippet.TrimEnd("`r","`n")
$lines2 += $lines[$insertPos..($lines.Length-1)]

[IO.File]::WriteAllLines($target, $lines2, [Text.Encoding]::UTF8)

# Compila; si falla, rollback
$py = ".\.venv\Scripts\python.exe"
& $py -m py_compile $target
if ($LASTEXITCODE -ne 0) {
  Write-Host "Compilación falló. Restaurando..." -ForegroundColor Yellow
  Copy-Item $bak $target -Force
  exit 1
}
Write-Host "A3 OK — weekdays→days_mask aplicado." -ForegroundColor Green

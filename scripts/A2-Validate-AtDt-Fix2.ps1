# scripts\A2-Validate-AtDt-Fix2.ps1
$ErrorActionPreference = "Stop"
$target = "app\routers\pos_coupons.py"
if (!(Test-Path $target)) { throw "No existe $target" }

# Evita duplicados
if (Select-String -Path $target -SimpleMatch "# AT_DT_PREP_FIX2_START" -Quiet) {
  Write-Host "A2 OK — snippet ya presente."
  exit 0
}

$bak = "$target.bak.A2.$((Get-Date).ToString('yyyyMMdd_HHmmss'))"
Copy-Item $target $bak -Force
$lines = Get-Content -Path $target

# 1) Localiza el handler y la línea def
$idxDecor = ($lines | Select-String -Pattern '^\s*@router\.post\("?/validate"' | Select-Object -First 1).LineNumber
if (-not $idxDecor) { throw "No se encontró @router.post('/validate')" }

$defMatch = $null
for ($i=$idxDecor; $i -lt $lines.Count; $i++) {
  if ($lines[$i] -match '^(?<ind>\s*)def\s+\w+\s*\(') { $defMatch = [pscustomobject]@{Idx=$i; Ind=$matches['ind']} ; break }
}
if (-not $defMatch) { throw "No se encontró def validate_coupon(" }

# 2) Encuentra el final de la firma (línea que contiene '):')
$endSig = $null
for ($j=$defMatch.Idx; $j -lt [Math]::Min($defMatch.Idx+50, $lines.Count); $j++) {
  if ($lines[$j] -match '\)\s*:') { $endSig = $j; break }
}
if (-not $endSig) { throw "No se encontró cierre de firma '):' de validate_coupon" }

$indent = $defMatch.Ind + "    "

# 3) Construye snippet (sin here-strings para evitar errores de parsing)
$S = @()
$S += $indent + "# AT_DT_PREP_FIX2_START"
$S += $indent + "try:"
$S += $indent + "    _wd = getattr(payload, 'weekday', None)"
$S += $indent + "    _at = getattr(payload, 'at', None)"
$S += $indent + "    at_dt = None"
$S += $indent + "    if _at:"
$S += $indent + "        try:"
$S += $indent + "            from datetime import datetime as _DT"
$S += $indent + "            at_dt = _DT.fromisoformat(_at)"
$S += $indent + "        except Exception:"
$S += $indent + "            at_dt = None"
$S += $indent + "    if (at_dt is None) and (_wd is not None):"
$S += $indent + "        if isinstance(_wd, str):"
$S += $indent + "            _map = {'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6,'lun':0,'mar':1,'mie':2,'jue':3,'vie':4,'sab':5,'dom':6}"
$S += $indent + "            try:"
$S += $indent + "                _wd_i = int(_wd)"
$S += $indent + "            except Exception:"
$S += $indent + "                _wd_i = _map.get(_wd.strip().lower()[:3], None)"
$S += $indent + "        else:"
$S += $indent + "            _wd_i = int(_wd)"
$S += $indent + "        if _wd_i is not None:"
$S += $indent + "            import datetime as _dt"
$S += $indent + "            _base = _dt.datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)"
$S += $indent + "            _shift = (_wd_i - _base.weekday()) % 7"
$S += $indent + "            at_dt = _base + _dt.timedelta(days=_shift)"
$S += $indent + "except Exception:"
$S += $indent + "    pass"
$S += $indent + "# AT_DT_PREP_FIX2_END"

# 4) Inserta el snippet justo DESPUÉS de la línea que cierra la firma
$before = $lines[0..$endSig]
$after  = $lines[($endSig+1)..($lines.Count-1)]
$new = @()
$new += $before
$new += $S
$new += $after
Set-Content -Path $target -Value $new -Encoding UTF8

# 5) Compila y confirma
$py = ".\.venv\Scripts\python.exe"
& $py -m py_compile $target
if ($LASTEXITCODE -ne 0) {
  Write-Host "Compilación falló. Restaurando $bak ..." -ForegroundColor Yellow
  Copy-Item $bak $target -Force
  exit 1
}
Write-Host "A2 OK — snippet insertado y compilado." -ForegroundColor Green

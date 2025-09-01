# scripts\A2-Validate-AtDt-Fix2B.ps1
$ErrorActionPreference = "Stop"
$target = "app\routers\pos_coupons.py"
if (!(Test-Path $target)) { throw "No existe $target" }

# Evita duplicados
if (Select-String -Path $target -SimpleMatch "# AT_DT_PREP_FIX2B_START" -Quiet) {
  Write-Host "A2b OK — snippet ya presente."
  exit 0
}

$bak = "$target.bak.A2b.$((Get-Date).ToString('yyyyMMdd_HHmmss'))"
Copy-Item $target $bak -Force
$lines = Get-Content -Path $target

# 1) Encuentra el bloque de validate y la llamada a compute_coupon_result(
$idxDecor = ($lines | Select-String -Pattern '^\s*@router\.post\("?/validate"' | Select-Object -First 1).LineNumber
if (-not $idxDecor) { throw "No se encontró @router.post('/validate')" }

$compute = $null
for ($i = $idxDecor; $i -lt [Math]::Min($idxDecor+500, $lines.Count); $i++) {
  if ($lines[$i] -match '^\s*res\s*=\s*compute_coupon_result\s*\(') { $compute = $i; break }
}
if (-not $compute) { throw "No se encontró la línea de llamada a compute_coupon_result(...)" }

$indent = ($lines[$compute] -replace '^(\s*).*','$1')

# 2) Construye snippet seguro (array de líneas, sin here-strings)
$S = @()
$S += $indent + "# AT_DT_PREP_FIX2B_START"
$S += $indent + "try:"
$S += $indent + "    _wd = getattr(payload, 'weekday', None)"
$S += $indent + "    _at = getattr(payload, 'at', None)"
$S += $indent + "    _tmp_at = None"
$S += $indent + "    if _at:"
$S += $indent + "        try:"
$S += $indent + "            from datetime import datetime as _DT"
$S += $indent + "            _tmp_at = _DT.fromisoformat(_at)"
$S += $indent + "        except Exception:"
$S += $indent + "            _tmp_at = None"
$S += $indent + "    if (_tmp_at is None) and (_wd is not None):"
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
$S += $indent + "            _tmp_at = _base + _dt.timedelta(days=_shift)"
$S += $indent + "    try:"
$S += $indent + "        at_dt"
$S += $indent + "    except Exception:"
$S += $indent + "        at_dt = None"
$S += $indent + "    if (at_dt is None) and (_tmp_at is not None):"
$S += $indent + "        at_dt = _tmp_at"
$S += $indent + "    # log de verificación"
$S += $indent + "    try:"
$S += $indent + "        import json, os"
$S += $indent + "        os.makedirs('data', exist_ok=True)"
$S += $indent + "        with open('data/debug_weekend15.log','a', encoding='utf-8') as _f:"
$S += $indent + "            _log = {"
$S += $indent + "                'DBG': 'validate_pre_call',"
$S += $indent + "                'code': getattr(payload, 'code', None),"
$S += $indent + "                'weekday': _wd,"
$S += $indent + "                'at': _at,"
$S += $indent + "                'at_dt': (at_dt.isoformat() if at_dt is not None else None)"
$S += $indent + "            }"
$S += $indent + "            _f.write(json.dumps(_log) + '\n')"
$S += $indent + "    except Exception:"
$S += $indent + "        pass"
$S += $indent + "except Exception:"
$S += $indent + "    pass"
$S += $indent + "# AT_DT_PREP_FIX2B_END"

# 3) Inserta justo ANTES de la llamada a compute_coupon_result
$before = $lines[0..($compute-2)]
$callAndAfter = $lines[($compute-1)..($lines.Count-1)]
$new = @()
$new += $before
$new += $S
$new += $callAndAfter
Set-Content -Path $target -Value $new -Encoding UTF8

# 4) Compila
$py = ".\.venv\Scripts\python.exe"
& $py -m py_compile $target
if ($LASTEXITCODE -ne 0) {
  Write-Host "Compilación falló. Restaurando $bak ..." -ForegroundColor Yellow
  Copy-Item $bak $target -Force
  exit 1
}
Write-Host "A2b OK — snippet insertado antes de compute_coupon_result() y compilado." -ForegroundColor Green

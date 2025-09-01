# scripts\A2-Validate-AtDt-Fix.ps1
$ErrorActionPreference = "Stop"
$target = "app\routers\pos_coupons.py"
if (!(Test-Path $target)) { throw "No existe $target" }

# Evita duplicado si ya lo insertaste antes
if (Select-String -Path $target -SimpleMatch "# AT_DT_PREP_FIX_START" -Quiet) {
  Write-Host "A2 OK — snippet ya presente."
  exit 0
}

$bak = "$target.bak.A2.$((Get-Date).ToString('yyyyMMdd_HHmmss'))"
Copy-Item $target $bak -Force

# Carga archivo completo
$txt = Get-Content -Path $target -Raw

# Busca el handler @router.post("/validate") y su def
$regex = [regex]'(?ms)^\s*@router\.post\("?/validate"?.*?\r?\n(?<ind>\s*)def\s+\w+\s*\('
$m = $regex.Match($txt)
if (-not $m.Success) { throw "No se encontró handler @router.post('/validate')" }

$ind = $m.Groups['ind'].Value + "    "

# Snippet Python que setea at_dt desde payload.at o payload.weekday
$snippet = @(
"$($ind)# AT_DT_PREP_FIX_START",
"$($ind)try:",
"$($ind)    _obj = locals().get('payload', None)",
"$($ind)    _wd = getattr(_obj, 'weekday', None) if _obj is not None else None",
"$($ind)    _at = getattr(_obj, 'at', None) if _obj is not None else None",
"$($ind)    at_dt = None",
"$($ind)    if _at:",
"$($ind)        try:",
"$($ind)            from datetime import datetime as _DT",
"$($ind)            at_dt = _DT.fromisoformat(_at)",
"$($ind)        except Exception:",
"$($ind)            at_dt = None",
"$($ind)    if (at_dt is None) and (_wd is not None):",
"$($ind)        if isinstance(_wd, str):",
"$($ind)            _map = {'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6,",
"$($ind)                    'lun':0,'mar':1,'mie':2,'jue':3,'vie':4,'sab':5,'dom':6}",
"$($ind)            try:",
"$($ind)                _wd_i = int(_wd)",
"$($ind)            except Exception:",
"$($ind)                _wd_i = _map.get(_wd.strip().lower()[:3], None)",
"$($ind)        else:",
"$($ind)            _wd_i = int(_wd)",
"$($ind)        if _wd_i is not None:",
"$($ind)            import datetime as _dt",
"$($ind)            _base = _dt.datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)",
"$($ind)            _shift = (_wd_i - _base.weekday()) % 7",
"$($ind)            at_dt = _base + _dt.timedelta(days=_shift)",
"$($ind)except Exception:",
"$($ind)    pass",
"$($ind)# AT_DT_PREP_FIX_END",
""
) -join "`n"

# Inserta inmediatamente DESPUÉS de la línea 'def validate_coupon(...):'
$insertPos = $m.Index + $m.Length
$txt2 = $txt.Substring(0, $insertPos) + $snippet + $txt.Substring($insertPos)
Set-Content -Path $target -Value $txt2 -Encoding UTF8

# Compila: si falla, restaura
$py = ".\.venv\Scripts\python.exe"
& $py -m py_compile $target
if ($LASTEXITCODE -ne 0) {
  Write-Host "Compilación falló. Restaurando $bak ..." -ForegroundColor Yellow
  Copy-Item $bak $target -Force
  exit 1
}
Write-Host "A2 OK — snippet insertado y compilado." -ForegroundColor Green

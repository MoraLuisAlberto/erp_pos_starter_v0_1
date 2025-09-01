# scripts\A0b-Validate-ReadWeekdayFromBody.ps1
$ErrorActionPreference = "Stop"
$target = "app\routers\pos_coupons.py"
if (!(Test-Path $target)) { throw "No existe $target" }
$bak = "$target.bak.A0b.$((Get-Date).ToString('yyyyMMdd_HHmmss'))"
Copy-Item $target $bak -Force

# Cargar archivo
$txt = Get-Content $target -Raw

# 1) Asegurar "Request" en import de fastapi
$txt = [regex]::Replace(
  $txt,
  '(^\s*from\s+fastapi\s+import\s+)([^\r\n]+)',
  {
    param($m)
    $base,$items = $m.Groups[1].Value, $m.Groups[2].Value
    if ($items -notmatch '\bRequest\b') { $items = $items.TrimEnd() + ", Request" }
    return $base + $items
  },
  [System.Text.RegularExpressions.RegexOptions]::Multiline
)

# 2) Localizar decorador/def del handler
$decorRx = '(?m)^[ \t]*@router\.post\("/validate"[^\r\n]*\)\s*\r?\n[ \t]*(?:def|async\s+def)\s+validate_coupon\s*\('
$mDecor = [regex]::Match($txt, $decorRx)
if (-not $mDecor.Success) { throw "No se encontró @router.post('/validate') + def/async def validate_coupon(" }

# 3) Convertir a async def y agregar request: Request si falta
$lineRx = '(?m)^[ \t]*(?:def|async\s+def)\s+validate_coupon\s*\((?<params>[^\)]*)\)\s*:'
$mLine = [regex]::Match($txt, $lineRx)
if (-not $mLine.Success) { throw "No se pudo localizar la línea de def/async def validate_coupon(...)" }

$params = $mLine.Groups['params'].Value
if ($params -notmatch '\bRequest\b') {
  if ($params.Trim() -eq '') { $newParams = 'request: Request' }
  else { $newParams = 'request: Request, ' + $params.Trim() }
} else { $newParams = $params }

$txt = [regex]::Replace($txt, $lineRx, {
  param($m)
  $ind = ([regex]::Match($m.Value,'^\s*')).Value
  "$($ind)async def validate_coupon($newParams):"
})

# 4) Insertar snippet justo después de la firma
$mLine2 = [regex]::Match($txt, '(?m)^[ \t]*async\s+def\s+validate_coupon\s*\([^\)]*\)\s*:\s*$')
if (-not $mLine2.Success) { throw "No se pudo ubicar la firma async def validate_coupon(...):" }

$ind = ([regex]::Match($mLine2.Value,'^\s*')).Value + "    "
$snippet = @"
$($ind)# A0b_WEEKDAY_FROM_BODY_START
$($ind)try:
$($ind)    _data = await request.json()
$($ind)    _wd = _data.get("weekday", None)
$($ind)    if _wd is not None:
$($ind)        try:
$($ind)            _map = {'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6,
$($ind)                    'lun':0,'mar':1,'mie':2,'jue':3,'vie':4,'sab':5,'dom':6}
$($ind)            if isinstance(_wd, str):
$($ind)                try:
$($ind)                    _wd_i = int(_wd)
$($ind)                except Exception:
$($ind)                    _wd_i = _map.get(_wd.strip().lower()[:3], _wd)
$($ind)                _wd = _wd_i
$($ind)            if (not hasattr(payload, "weekday")) or (getattr(payload,"weekday",None) is None):
$($ind)                setattr(payload, "weekday", _wd)
$($ind)        except Exception:
$($ind)            pass
$($ind)except Exception:
$($ind)    pass
$($ind)# A0b_WEEKDAY_FROM_BODY_END
"@

$insertPos = $mLine2.Index + $mLine2.Length
$txt = $txt.Substring(0,$insertPos) + "`r`n" + $snippet + $txt.Substring($insertPos)

# 5) Guardar y compilar
Set-Content -Path $target -Value $txt -Encoding UTF8
$py = ".\.venv\Scripts\python.exe"
& $py -m py_compile $target
if ($LASTEXITCODE -ne 0) {
  Write-Host "Compilación falló. Restaurando $bak ..." -ForegroundColor Yellow
  Copy-Item $bak $target -Force
  exit 1
}
Write-Host "A0b OK — handler async, Request añadido y weekday leído del body." -ForegroundColor Green

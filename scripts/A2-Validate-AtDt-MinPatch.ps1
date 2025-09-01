$ErrorActionPreference = "Stop"
$target = "app\routers\pos_coupons.py"
if (!(Test-Path $target)) { throw "No existe $target" }

# Evita duplicar si ya está el snippet
if (Select-String -Path $target -SimpleMatch "# AT_DT_PREP_SNIPPET_START" -Quiet) {
  Write-Host "A2 SKIP — snippet ya existe." -ForegroundColor Yellow
  exit 0
}

$bak = "$target.bak.A2"
Copy-Item $target $bak -Force

# Carga
$lines = [IO.File]::ReadAllLines($target)
$N = $lines.Length

# Encuentra def validate_coupon(
$defMatch = Select-String -InputObject $lines -Pattern '^\s*def\s+validate_coupon\s*\(' -List
if (-not $defMatch) { throw "No se encontró def validate_coupon(" }
$defIdx = $defMatch.LineNumber - 1  # zero-based

# Busca una llamada a compute_coupon_result( dentro del handler (hasta el siguiente def)
$idxCall = $null
for ($i = $defIdx + 1; $i -lt $N; $i++) {
  if ($i -gt $defIdx + 1 -and $lines[$i] -match '^\s*def\s+') { break }
  if ($lines[$i] -match 'compute_coupon_result\s*\(') { $idxCall = $i; break }
}

# Decide dónde insertar
$insertAt = $null
if ($idxCall -ne $null) {
  $insertAt = $idxCall
} else {
  # Inserta al inicio del cuerpo del handler, respetando docstring si existe
  $insertAt = $defIdx + 1
  # salta líneas en blanco y comentarios
  while ($insertAt -lt $N -and ($lines[$insertAt].Trim() -eq "" -or $lines[$insertAt].TrimStart().StartsWith("#"))) {
    $insertAt++
  }
  # si hay docstring triple, saltarlo completo
  if ($insertAt -lt $N) {
    $trim = $lines[$insertAt].Trim()
    if ($trim.StartsWith('"""') -or $trim.StartsWith("'''")) {
      $quote = if ($trim.StartsWith('"""')) { '"""' } else { "'''" }
      $insertAt++
      while ($insertAt -lt $N -and -not ($lines[$insertAt].Contains($quote))) { $insertAt++ }
      if ($insertAt -lt $N) { $insertAt++ }
    }
  }
}

# Calcula indent
$indent = ""
if ($idxCall -ne $null) {
  if ($lines[$idxCall] -match '^\s*') { $indent = $matches[0] }
} else {
  # indent de la primera línea efectiva del cuerpo o def+4
  if ($insertAt -lt $N -and ($lines[$insertAt] -match '^\s*')) {
    $indent = $matches[0]
  } else {
    ($lines[$defIdx] -match '^\s*') | Out-Null
    $indent = $matches[0] + "    "
  }
}

# Snippet
$snippet = @"
$($indent)# AT_DT_PREP_SNIPPET_START
$($indent)try:
$($indent)    if 'at_dt' not in locals() or at_dt is None:
$($indent)        _at = getattr(payload, 'at', None)
$($indent)        if _at:
$($indent)            from datetime import datetime as _DT
$($indent)            try:
$($indent)                at_dt = _DT.fromisoformat(_at)
$($indent)            except Exception:
$($indent)                at_dt = None
$($indent)    if ('at_dt' not in locals() or at_dt is None) and hasattr(payload, 'weekday'):
$($indent)        _wd = getattr(payload, 'weekday', None)
$($indent)        if _wd is not None:
$($indent)            _map = {'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6,'lun':0,'mar':1,'mie':2,'jue':3,'vie':4,'sab':5,'dom':6}
$($indent)            try:
$($indent)                _wd_i = int(_wd)
$($indent)            except Exception:
$($indent)                _wd_i = _map.get(str(_wd).strip().lower()[:3], None)
$($indent)            if _wd_i is not None:
$($indent)                import datetime as _dt
$($indent)                _base = _dt.datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
$($indent)                _shift = (int(_wd_i) - _base.weekday()) % 7
$($indent)                at_dt = _base + _dt.timedelta(days=_shift)
$($indent)except Exception:
$($indent)    pass
$($indent)# AT_DT_PREP_SNIPPET_END
"@

# Inserta
$before = if ($insertAt -gt 0) { $lines[0..($insertAt-1)] } else { @() }
$after  = if ($insertAt -lt $N) { $lines[$insertAt..($N-1)] } else { @() }
$linesNew = @()
$linesNew += $before
$linesNew += $snippet.TrimEnd("`r","`n")
$linesNew += $after

[IO.File]::WriteAllLines($target, $linesNew, [Text.Encoding]::UTF8)

# Compila; si falla, rollback
$py = ".\.venv\Scripts\python.exe"
& $py -m py_compile $target
if ($LASTEXITCODE -ne 0) {
  Write-Host "Compilación falló. Restaurando..." -ForegroundColor Yellow
  Copy-Item $bak $target -Force
  exit 1
}
Write-Host "A2 OK — at_dt preparado en validate_coupon()." -ForegroundColor Green

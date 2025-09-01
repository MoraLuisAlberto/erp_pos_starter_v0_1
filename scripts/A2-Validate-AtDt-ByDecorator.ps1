$ErrorActionPreference = "Stop"
$target = "app\routers\pos_coupons.py"
if (!(Test-Path $target)) { throw "No existe $target" }

# Evita duplicados
if (Select-String -Path $target -SimpleMatch "# AT_DT_PREP_SNIPPET_START" -Quiet) {
  Write-Host "A2 SKIP — snippet ya existe."
  exit 0
}

$bak = "$target.bak.A2b.$((Get-Date).ToString('yyyyMMdd_HHmmss'))"
Copy-Item $target $bak -Force

# Cargar
[string[]]$lines = [IO.File]::ReadAllLines($target)
$N = $lines.Length

# 1) Ubicar el decorador @router.post("/validate")
$decIdx = $null
for ($i=0; $i -lt $N; $i++) {
  if ($lines[$i] -match '^\s*@router\.post\(\s*["'']\/validate["'']') { $decIdx = $i; break }
}
if ($decIdx -eq $null) { throw "No se encontró @router.post(""/validate"")" }

# 2) La siguiente línea 'def ...('
$defIdx = $null
for ($j=$decIdx+1; $j -lt $N; $j++) {
  if ($lines[$j] -match '^\s*def\s+\w+\s*\(') { $defIdx = $j; break }
  if ($lines[$j] -match '^\s*@router\.post\(') { break } # otro handler: abortar
}
if ($defIdx -eq $null) { throw "No se encontró la línea def del handler después del decorador" }

# 3) Calcular indentaciones
$null = ($lines[$defIdx] -match '^(?<ind>\s*)')
$defIndent   = $matches['ind']
$bodyIndent  = $defIndent + '    '

# 4) Definir posición de inserción:
#    - Si hay llamada a compute_coupon_result(...) dentro del handler, insertar justo antes.
#    - Si no, insertar al inicio del cuerpo (saltando docstring/comentarios iniciales).
$nextDefOrDecorator = $N
for ($k=$defIdx+1; $k -lt $N; $k++) {
  if ($lines[$k] -match '^\s*def\s+\w+\s*\(' -or $lines[$k] -match '^\s*@router\.post\(') { $nextDefOrDecorator = $k; break }
}
$idxCall = $null
for ($k=$defIdx+1; $k -lt $nextDefOrDecorator; $k++) {
  if ($lines[$k] -match 'compute_coupon_result\s*\(') { $idxCall = $k; break }
}

$insertAt = $null
if ($idxCall -ne $null) {
  $insertAt = $idxCall
} else {
  # Inicio del cuerpo tras def
  $insertAt = $defIdx + 1
  # Saltar líneas en blanco y comentarios
  while ($insertAt -lt $nextDefOrDecorator -and ($lines[$insertAt].Trim() -eq '' -or $lines[$insertAt].TrimStart().StartsWith('#'))) {
    $insertAt++
  }
  # Saltar docstring triple si existe
  if ($insertAt -lt $nextDefOrDecorator) {
    $t = $lines[$insertAt].Trim()
    if ($t.StartsWith('"""') -or $t.StartsWith("'''")) {
      $q = if ($t.StartsWith('"""')) { '"""' } else { "'''" }
      # Caso docstring de una sola línea
      if (-not $t.EndsWith($q)) {
        $insertAt++
        while ($insertAt -lt $nextDefOrDecorator -and -not ($lines[$insertAt].Contains($q))) { $insertAt++ }
        if ($insertAt -lt $nextDefOrDecorator) { $insertAt++ }
      } else {
        $insertAt++
      }
    }
  }
}

# 5) Construir snippet (como array de líneas para evitar interpolaciones raras)
$S = @()
$S += "$bodyIndent# AT_DT_PREP_SNIPPET_START"
$S += "$bodyIndent""try:"""
$S += "$bodyIndent    if 'at_dt' not in locals() or at_dt is None:"
$S += "$bodyIndent        _at = getattr(payload, 'at', None)"
$S += "$bodyIndent        if _at:"
$S += "$bodyIndent            from datetime import datetime as _DT"
$S += "$bodyIndent            try:"
$S += "$bodyIndent                at_dt = _DT.fromisoformat(_at)"
$S += "$bodyIndent            except Exception:"
$S += "$bodyIndent                at_dt = None"
$S += "$bodyIndent    if ('at_dt' not in locals() or at_dt is None) and hasattr(payload, 'weekday'):"
$S += "$bodyIndent        _wd = getattr(payload, 'weekday', None)"
$S += "$bodyIndent        if _wd is not None:"
$S += "$bodyIndent            _map = {'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6,'lun':0,'mar':1,'mie':2,'jue':3,'vie':4,'sab':5,'dom':6}"
$S += "$bodyIndent            try:"
$S += "$bodyIndent                _wd_i = int(_wd)"
$S += "$bodyIndent            except Exception:"
$S += "$bodyIndent                _wd_i = _map.get(str(_wd).strip().lower()[:3], None)"
$S += "$bodyIndent            if _wd_i is not None:"
$S += "$bodyIndent                import datetime as _dt"
$S += "$bodyIndent                _base = _dt.datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)"
$S += "$bodyIndent                _shift = (int(_wd_i) - _base.weekday()) % 7"
$S += "$bodyIndent                at_dt = _base + _dt.timedelta(days=_shift)"
$S += "$bodyIndent""except Exception:"""
$S += "$bodyIndent    pass"
$S += "$bodyIndent# AT_DT_PREP_SNIPPET_END"

# 6) Insertar
$before = if ($insertAt -gt 0) { $lines[0..($insertAt-1)] } else { @() }
$after  = if ($insertAt -lt $N) { $lines[$insertAt..($N-1)] } else { @() }
$linesNew = @()
$linesNew += $before
$linesNew += $S
$linesNew += $after

[IO.File]::WriteAllLines($target, $linesNew, [Text.Encoding]::UTF8)

# 7) Compilar; si falla, rollback
$py = ".\.venv\Scripts\python.exe"
& $py -m py_compile $target
if ($LASTEXITCODE -ne 0) {
  Write-Host "Compilación falló. Restaurando $bak ..." -ForegroundColor Yellow
  Copy-Item $bak $target -Force
  exit 1
}
Write-Host "A2b OK — at_dt preparado dentro del handler /validate." -ForegroundColor Green

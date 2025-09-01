# .\scripts\A4-Debug-Weekend15.ps1
$ErrorActionPreference = "Stop"
$target = "app\routers\pos_coupons.py"
if (!(Test-Path $target)) { throw "No existe $target" }

# Evitar duplicado
if (Select-String -Path $target -SimpleMatch "# DBG_WEEKEND15_START" -Quiet) {
  Write-Host "A4 SKIP — snippet ya existe."
  exit 0
}

$bak = "$target.bak.A4.$((Get-Date).ToString('yyyyMMdd_HHmmss'))"
Copy-Item $target $bak -Force

# Leer archivo
[string[]]$lines = [IO.File]::ReadAllLines($target)
$N = $lines.Length

# Buscar la línea: rule = COUPONS.get(code_up)
$ruleIdx = $null
for ($i=0; $i -lt $N; $i++) {
  if ($lines[$i] -match '^\s*rule\s*=\s*COUPONS\.get\(code_up\)') { $ruleIdx = $i; break }
}
if ($ruleIdx -eq $null) { throw "No se encontró 'rule = COUPONS.get(code_up)'" }

# Indent del cuerpo de la función
$null = ($lines[$ruleIdx] -match '^(?<ind>\s*)')
$indent = $matches['ind']

# Snippet Python (usar $($indent) para delimitar variable antes de texto)
$S = @()
$S += "$($indent)# DBG_WEEKEND15_START"
$S += "$($indent)try:"
$S += "$($indent)    _dbg = {"
$S += "$($indent)        'DBG': 'wkd_check',"
$S += "$($indent)        'code': code_up,"
$S += "$($indent)        'at_dt': (at_dt.isoformat() if at_dt else None),"
$S += "$($indent)        'weekday': (at_dt.weekday() if at_dt else None),"
$S += "$($indent)        'rule_weekdays': (rule.get('weekdays') if isinstance(rule, dict) else None),"
$S += "$($indent)        'rule_days_mask': (rule.get('days_mask') if isinstance(rule, dict) else None)"
$S += "$($indent)    }"
$S += "$($indent)    import json, os"
$S += "$($indent)    os.makedirs('data', exist_ok=True)"
$S += "$($indent)    with open('data/debug_weekend15.log','a', encoding='utf-8') as _f:"
$S += "$($indent)        _f.write(json.dumps(_dbg, ensure_ascii=False) + '\n')"
$S += "$($indent)except Exception:"
$S += "$($indent)    pass"
$S += "$($indent)# DBG_WEEKEND15_END"

# Insertar justo después de 'rule = ...'
$before = if ($ruleIdx -ge 0) { $lines[0..$ruleIdx] } else { @() }
$after  = if ($ruleIdx+1 -lt $N) { $lines[($ruleIdx+1)..($N-1)] } else { @() }
$linesNew = @(); $linesNew += $before; $linesNew += $S; $linesNew += $after
[IO.File]::WriteAllLines($target, $linesNew, [Text.Encoding]::UTF8)

# Compilar
$py = ".\.venv\Scripts\python.exe"
& $py -m py_compile $target
if ($LASTEXITCODE -ne 0) {
  Write-Host "Compilación falló. Restaurando $bak ..." -ForegroundColor Yellow
  Copy-Item $bak $target -Force
  exit 1
}
Write-Host "A4 OK — debug insertado." -ForegroundColor Green

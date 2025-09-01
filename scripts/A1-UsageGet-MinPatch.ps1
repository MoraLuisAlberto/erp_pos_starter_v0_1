$ErrorActionPreference = "Stop"
$target = "app\routers\pos_coupons.py"
if (!(Test-Path $target)) { throw "No existe $target" }
$bak = "$target.bak.A1"

Copy-Item $target $bak -Force

# Lee archivo completo
$text = [IO.File]::ReadAllText($target)

# Nueva función (respetar sangría de la primera columna)
$newFunc = @"
def usage_get(code: str, customer_id: Optional[int]) -> Tuple[int, Optional[int], Optional[int]]:
    key = (code, int(customer_id)) if customer_id is not None else (code, -1)
    used = _USAGE.get(key, 0)
    rule = COUPONS.get(code, {})
    max_uses = rule.get("max_uses")
    remaining = (max_uses - used) if isinstance(max_uses, int) else None
    return used, max_uses, remaining
"@

# Regex: desde 'def usage_get(' hasta el próximo 'def ' al inicio de línea o EOF
$rx = [regex]::new("(?ms)^\s*def\s+usage_get\s*\(.*?\):.*?(?=^\s*def\s+|\Z)")
if ($rx.IsMatch($text)) {
  $text2 = $rx.Replace($text, $newFunc, 1)
} else {
  throw "No se encontró def usage_get(...)"
}

[IO.File]::WriteAllText($target, $text2, [Text.Encoding]::UTF8)

# Compila; si falla, rollback
$py = ".\.venv\Scripts\python.exe"
& $py -m py_compile $target
if ($LASTEXITCODE -ne 0) {
  Write-Host "Compilación falló. Restaurando..." -ForegroundColor Yellow
  Copy-Item $bak $target -Force
  exit 1
}
Write-Host "A1 OK  — usage_get reemplazado y compilado." -ForegroundColor Green

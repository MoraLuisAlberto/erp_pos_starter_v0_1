param(
  [string]$MainPath = "app\main.py"
)

# 1) Cargar
$main = Get-Content $MainPath -Raw
$changed = $false

# 2) Asegurar el import (una sola vez)
if ($main -notmatch 'from\s+app\.middleware\.pay_audit\s+import\s+install_pay_audit') {
  $main = $main -replace '(^\s*from\s+fastapi\s+import\s+FastAPI[^\r\n]*\r?\n)',
    '$1from app.middleware.pay_audit import install_pay_audit' + "`r`n"
  $changed = $true
}

# 3) Insertar la llamada tras app = FastAPI(...)
if ($main -notmatch 'install_pay_audit\s*\(app\)') {
  $replacement = '$1' + "`r`ninstall_pay_audit(app)`r`n"
  # Usamos Regex.Replace con reemplazo ya concatenado (evita el error del operador -replace)
  $main = [regex]::Replace($main, '(app\s*=\s*FastAPI\([^\)]*\)\s*)', $replacement, 1)
  $changed = $true
}

# 4) Guardar si hubo cambios
if ($changed) {
  Set-Content -Path $MainPath -Value $main -Encoding UTF8
  Write-Host ">> main.py parchado."
} else {
  Write-Host ">> main.py ya estaba OK (sin cambios)."
}

# 5) Mostrar línea de control
Write-Host "`n-- grep install_pay_audit --"
Select-String -Path $MainPath -Pattern 'install_pay_audit' -Context 0,1 | ForEach-Object {
  $_.Line
  if ($_.Context.PostContext) { $_.Context.PostContext }
}

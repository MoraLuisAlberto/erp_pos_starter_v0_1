# A-weekend15-min.ps1
# Parche directo: asegurar days_mask sabado(5) y domingo(6) para WEEKEND15.
# Ejecutar desde la raiz del repo.

$ErrorActionPreference = "Stop"

function Timestamp { (Get-Date).ToString("yyyyMMdd_HHmmss") }

function Compile-All {
  Write-Host "==> Validando sintaxis Python (py_compile) ..."
  $py = ".\.venv\Scripts\python.exe"
  if (-not (Test-Path $py)) { throw "No se encontro $py" }
  $files = Get-ChildItem -Recurse -Include *.py | ForEach-Object { $_.FullName }
  if (-not $files -or $files.Count -eq 0) { return }
  $code = "import py_compile,sys; ok=1; files=sys.argv[1:]; " +
          "for f in files: " +
          "  try: py_compile.compile(f, doraise=True) " +
          "  except Exception as e: " +
          "    print('COMPILE_ERROR:', f, e); ok=0 " +
          "sys.exit(0 if ok else 1)"
  & $py -c $code @files
  if ($LASTEXITCODE -ne 0) { throw "Compilacion fallida" }
}

function Run-Pytest {
  param([string]$NodeId)
  Write-Host "==> Pytest: $NodeId"
  & .\.venv\Scripts\pytest.exe -q $NodeId
  return $LASTEXITCODE
}

$target = "app\routers\pos_coupons.py"
if (-not (Test-Path $target)) { throw "No se encontro $target" }

$ts = Timestamp
$backup = "$($target).bak.$ts"
Copy-Item $target $backup -Force
Write-Host "Backup creado: $backup"

$text = Get-Content $target -Raw
$idx = $text.IndexOf("WEEKEND15")
if ($idx -lt 0) {
  Write-Host "No se encontro 'WEEKEND15' en $target. Restaurando backup..."
  Copy-Item $backup $target -Force
  exit 1
}

# Busca el primer delimitador de bloque { o ( despues de WEEKEND15
$openPos = -1
$openChar = ""
for ($i = $idx; $i -lt $text.Length; $i++) {
  $ch = $text[$i]
  if ($ch -eq '{' -or $ch -eq '(') { $openPos = $i; $openChar = $ch; break }
  if ($ch -eq '}' -or $ch -eq ')') { break }
}
if ($openPos -lt 0) {
  Write-Host "No se encontro inicio de bloque { o ( para WEEKEND15. Restaurando..."
  Copy-Item $backup $target -Force
  exit 1
}

$closeChar = (if ($openChar -eq '{') '}' else ')')

# Encontrar cierre equilibrado del bloque
$depth = 0
$closePos = -1
for ($j = $openPos; $j -lt $text.Length; $j++) {
  $ch = $text[$j]
  if ($ch -eq $openChar) { $depth++ }
  elseif ($ch -eq $closeChar) {
    $depth--
    if ($depth -eq 0) { $closePos = $j; break }
  }
}
if ($closePos -lt 0) {
  Write-Host "No se encontro cierre del bloque para WEEKEND15. Restaurando..."
  Copy-Item $backup $target -Force
  exit 1
}

$before = $text.Substring(0, $openPos+1)
$block  = $text.Substring($openPos+1, $closePos - ($openPos+1))
$after  = $text.Substring($closePos)

# Normaliza saltos para inspeccion simple
$blockTrim = $block.Trim()

# Definir como insertar/sustituir days_mask
$insertDict = "    days_mask: (1<<5) | (1<<6),"
$insertKw   = "days_mask=(1<<5) | (1<<6), "

if ($openChar -eq '{') {
  # Estilo diccionario: clave: valor
  if ($block -match "\bdays_mask\s*:") {
    $block2 = [regex]::Replace($block, "(\bdays_mask\s*:\s*)([^,}\r\n]+)", '$1(1<<5) | (1<<6)', 1)
  } else {
    # Insertar al inicio del dict
    $block2 = "`r`n" + $insertDict + "`r`n" + $blockTrim
  }
} else {
  # Estilo kwargs: clave=valor
  if ($block -match "\bdays_mask\s*=") {
    $block2 = [regex]::Replace($block, "(\bdays_mask\s*=\s*)([^,)\r\n]+)", '$1(1<<5) | (1<<6)', 1)
  } else {
    # Insertar al inicio de los kwargs
    $block2 = $insertKw + $blockTrim
  }
}

$newText = $before + $block2 + $after

# Mostrar diff de contexto (5 lineas antes y despues)
Write-Host "==> Contexto antes:"
$ctxBefore = $text.Substring([Math]::Max(0,$idx-200), [Math]::Min(200, $text.Length- [Math]::Max(0,$idx-200)))
Write-Host $ctxBefore
Write-Host "==> Contexto despues (nuevo):"
$ctxAfterIdx = $newText.IndexOf("WEEKEND15")
$ctxAfter = $newText.Substring([Math]::Max(0,$ctxAfterIdx-200), [Math]::Min(200, $newText.Length- [Math]::Max(0,$ctxAfterIdx-200)))
Write-Host $ctxAfter

Set-Content -Path $target -Value $newText -Encoding UTF8
Write-Host "Parche aplicado en $target"

try {
  Compile-All
} catch {
  Write-Host "ERROR: Compilacion fallo. Restaurando backup..."
  Copy-Item $backup $target -Force
  exit 1
}

# Ejecuta el test de borde
$node = "tests\test_coupon_rules_edges.py::test_time_windows_extra_edges"
$rc = Run-Pytest -NodeId $node
if ($rc -ne 0) {
  Write-Host "El test aun falla. Revisa la salida de pytest."
  exit 2
}

Write-Host "OK: Test paso."
Write-Host "Resumen:"
Write-Host " - Archivo: $target"
Write-Host " - Backup:  $backup"
Write-Host " - Test:    $node"

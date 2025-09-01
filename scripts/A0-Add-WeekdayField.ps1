# scripts\A0-Add-WeekdayField.ps1
$ErrorActionPreference = "Stop"
$target = "app\routers\pos_coupons.py"
if (!(Test-Path $target)) { throw "No existe $target" }
$bak = "$target.bak.A0.$((Get-Date).ToString('yyyyMMdd_HHmmss'))"
Copy-Item $target $bak -Force

$lines = Get-Content -Path $target

# 1) Asegurar 'Union' en los imports de typing
$typingMatches = Select-String -InputObject $lines -Pattern '^\s*from\s+typing\s+import\s+(.+)$' -AllMatches
$hasUnion = $false
$typingIdx = $null
foreach ($m in $typingMatches) {
  if ($m.Matches[0].Groups[1].Value -match '\bUnion\b') { $hasUnion = $true }
  if (-not $typingIdx) { $typingIdx = $m.LineNumber - 1 }
}
if (-not $hasUnion) {
  if ($typingIdx -ne $null) {
    # Anexar Union a la línea existente
    $lines[$typingIdx] = $lines[$typingIdx].TrimEnd() + ", Union"
  } else {
    # Insertar un import nuevo de Union tras el primer bloque de imports
    $ins = 0
    for ($i=0; $i -lt $lines.Count; $i++) {
      if ($lines[$i] -match '^\s*(from|import)\s+') { $ins = $i+1 } else { if ($ins -gt 0) { break } }
    }
    $lines = $lines[0..($ins-1)] + @("from typing import Union") + $lines[$ins..($lines.Count-1)]
  }
}

# 2) Localizar la clase CouponValidateRequest
$classMatch = Select-String -InputObject $lines -Pattern '^\s*class\s+CouponValidateRequest\s*\(' | Select-Object -First 1
if (-not $classMatch) { throw "No se encontró class CouponValidateRequest(" }
$classLine = $classMatch.LineNumber - 1

# Calcular indent del class
$clsIndent = ([regex]::Match($lines[$classLine], '^\s*')).Value
$bodyIndent = $clsIndent + "    "

# 3) Determinar fin del bloque de la clase y verificar si ya hay 'weekday:'
$endIdx = $lines.Count - 1
for ($i=$classLine+1; $i -lt $lines.Count; $i++) {
  # si aparece otro class/def con indent <= indent de la clase, terminó
  $m = [regex]::Match($lines[$i], '^(?<ind>\s*)(class|def)\s+')
  if ($m.Success -and ($m.Groups['ind'].Value.Length -le $clsIndent.Length)) {
    $endIdx = $i - 1; break
  }
}
$hasWeekday = $false
for ($j=$classLine+1; $j -le $endIdx; $j++) {
  if ($lines[$j] -match '^\s*weekday\s*:') { $hasWeekday = $true; break }
}

if (-not $hasWeekday) {
  $newAttr = $bodyIndent + "weekday: Optional[Union[int, str]] = None"
  # Insertar justo después de la línea 'class ...'
  $lines = $lines[0..$classLine] + @($newAttr) + $lines[($classLine+1)..($lines.Count-1)]
} else {
  Write-Host "A0 OK — 'weekday' ya existe en CouponValidateRequest."
}

# 4) Guardar y compilar
Set-Content -Path $target -Value $lines -Encoding UTF8
$py = ".\.venv\Scripts\python.exe"
& $py -m py_compile $target
if ($LASTEXITCODE -ne 0) {
  Write-Host "Compilación falló. Restaurando $bak ..." -ForegroundColor Yellow
  Copy-Item $bak $target -Force
  exit 1
}
Write-Host "A0 OK — weekday añadido al modelo y compilado." -ForegroundColor Green

# scripts\Patch-Weekend15.ps1
# Parchea app\routers\pos_coupons.py:
# 1) Reemplaza usage_get(...) por una versión mínima y segura.
# 2) Inserta preparación de at_dt en validate_coupon(...) (a partir de at/weekday).
# 3) Agrega soporte 'weekdays' en compute_coupon_result(...).
# Hace backup y valida con py_compile; si falla, restaura.

$ErrorActionPreference = "Stop"

function Compile-File([string]$file) {
  $py = ".\.venv\Scripts\python.exe"
  if (-not (Test-Path $py)) { throw "No se encontró $py" }
  & $py - << 'PY'
import sys, py_compile
fn = sys.argv[1]
py_compile.compile(fn, doraise=True)
print("OK")
PY
  if ($LASTEXITCODE -ne 0) { throw "py_compile falló para $file" }
}

$target = "app\routers\pos_coupons.py"
if (-not (Test-Path $target)) { throw "No existe $target" }

$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$bak = "$target.bak.$ts"
Copy-Item $target $bak -Force
Write-Host "Backup: $bak"

# Cargar
$txt = Get-Content $target -Raw

# -------------------------------------------------------------------
# A) Asegurar import de timedelta
# -------------------------------------------------------------------
$rxDt = [regex]'(?m)^\s*from\s+datetime\s+import\s+([^\r\n]+)'
$mDt = $rxDt.Match($txt)
if ($mDt.Success) {
  $line = $mDt.Value
  if ($line -notmatch '\btimedelta\b') {
    $line2 = $line.TrimEnd() -replace '\s*$', ', timedelta'
    $txt = $txt.Substring(0,$mDt.Index) + $line2 + $txt.Substring($mDt.Index + $mDt.Length)
    Write-Host "[OK] Agregado 'timedelta' al import de datetime."
  }
} else {
  # Si no hay esa forma de import, intentamos agregar una nueva línea segura cerca del tope
  $insertAt = 0
  $firstImport = [regex]::Match($txt,'(?m)^\s*import\s+\w+|^\s*from\s+\w+','Multiline')
  if ($firstImport.Success) { $insertAt = $firstImport.Index + $firstImport.Length }
  $txt = $txt.Insert($insertAt, "`r`nfrom datetime import timedelta`r`n")
  Write-Host "[OK] Insertado 'from datetime import timedelta'."
}

# -------------------------------------------------------------------
# B) Paso 1 — Reemplazar usage_get(...)
# -------------------------------------------------------------------
$newUsage = @'
def usage_get(code: str, customer_id: Optional[int]) -> Tuple[int, Optional[int], Optional[int]]:
    """Return (used, max_uses, remaining) without side-effects."""
    try:
        used = 0
        if customer_id is not None:
            used = _USAGE.get((code, customer_id), 0)
        rule = COUPONS.get(code, {}) if isinstance(code, str) else {}
        max_uses = rule.get("max_uses")
        remaining = (max_uses - used) if isinstance(max_uses, int) else None
        return used, max_uses, remaining
    except Exception:
        return 0, None, None
'@

$rxUsage = [regex]'(?s)^\s*def\s+usage_get\s*\([^\)]*\)\s*:\s*.*?(?=^\s*def\s+\w+\s*\(|\Z)'
if ($rxUsage.IsMatch($txt)) {
  $txt = $rxUsage.Replace($txt, $newUsage, 1)
  Write-Host "[OK] usage_get reemplazado."
} else {
  # Insertar después de la declaración de _USAGE si existe
  $rxU = [regex]'(?m)^\s*_USAGE\s*=\s*.*$'
  $mU  = $rxU.Match($txt)
  if ($mU.Success) {
    $insPos = $mU.Index + $mU.Length
    $txt = $txt.Insert($insPos, "`r`n`r`n$newUsage`r`n")
    Write-Host "[OK] usage_get insertado tras _USAGE."
  } else {
    # fallback: al final del archivo
    $txt += "`r`n`r`n$newUsage`r`n"
    Write-Host "[OK] usage_get agregado al final (no se encontró _USAGE)."
  }
}

# -------------------------------------------------------------------
# C) Paso 2 — Insertar preparación de at_dt en validate_coupon(...)
#     (idempotente via marcador AT_DT_PREP_SNIPPET_START)
# -------------------------------------------------------------------
if ($txt -notmatch 'AT_DT_PREP_SNIPPET_START') {
  $rxDefVal = [regex]'(?m)^(?<ind>[ \t]*)def\s+validate_coupon\s*\([^\)]*\)\s*:\s*$'
  $mVal = $rxDefVal.Match($txt)
  if ($mVal.Success) {
    $indent = $mVal.Groups['ind'].Value + '    '

    $prepCore = @'
# AT_DT_PREP_SNIPPET_START
at_dt = None
if getattr(payload, "at", None):
    try:
        at_dt = datetime.fromisoformat(payload.at)
    except Exception:
        at_dt = None
if at_dt is None and getattr(payload, "weekday", None) is not None:
    wd = payload.weekday
    if isinstance(wd, str):
        _map = {'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6,
                'lun':0,'mar':1,'mie':2,'jue':3,'vie':4,'sab':5,'dom':6}
        try:
            wd = int(wd)
        except Exception:
            wd = _map.get(wd.strip().lower()[:3], wd)
    base = datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    shift = (int(wd) - base.weekday()) % 7
    at_dt = base + timedelta(days=shift)
# AT_DT_PREP_SNIPPET_END

'@
    $prepIndented = ($indent) + ($prepCore -replace "`n","`n$indent")

    # Insertar justo después de la línea 'def validate_coupon...:'
    $defLineStart = $mVal.Index
    $defLineEnd   = $mVal.Index + $mVal.Length
    # insertar tras el salto de línea siguiente
    $nlIdx = $txt.IndexOf("`n", $defLineEnd)
    if ($nlIdx -ge 0) { $insertAt = $nlIdx + 1 } else { $insertAt = $defLineEnd }
    $txt = $txt.Insert($insertAt, $prepIndented)
    Write-Host "[OK] Snippet at_dt insertado en validate_coupon()."
  } else {
    Write-Host "[WARN] No se encontró def validate_coupon(...). Se omite Paso 2."
  }
} else {
  Write-Host "[SKIP] Snippet at_dt ya presente."
}

# -------------------------------------------------------------------
# D) Paso 3 — Agregar soporte 'weekdays' en compute_coupon_result(...)
#     (idempotente via marcador WEEKDAYS_SUPPORT_START)
# -------------------------------------------------------------------
if ($txt -notmatch 'WEEKDAYS_SUPPORT_START') {
  $rxDefCR = [regex]'(?m)^(?<ind>[ \t]*)def\s+compute_coupon_result\s*\([^\)]*\)\s*:\s*$'
  $mCR = $rxDefCR.Match($txt)
  if ($mCR.Success) {
    $funIndent = $mCR.Groups['ind'].Value + '    '

    # Encontrar la línea 'rule = COUPONS.get(...)' dentro de la función
    $afterFun = $txt.Substring($mCR.Index)
    $mRule = [regex]::Match($afterFun, '(?m)^[ \t]*rule\s*=\s*COUPONS\.get\([^\r\n]*\)\s*$')
    if ($mRule.Success) {
      $ruleAbsIdx = $mCR.Index + $mRule.Index + $mRule.Length
      # Insertar tras fin de línea
      $nlIdx2 = $txt.IndexOf("`n", $ruleAbsIdx)
      if ($nlIdx2 -ge 0) { $insertAt2 = $nlIdx2 + 1 } else { $insertAt2 = $ruleAbsIdx }

      $wkdCore = @'
# WEEKDAYS_SUPPORT_START
_wds = None
try:
    _wds = rule.get("weekdays")
except Exception:
    _wds = None
if _wds is not None:
    _map = {'mon':0,'tue':1,'wed':2,'thu':3,'fri':4,'sat':5,'sun':6,
            'lun':0,'mar':1,'mie':2,'jue':3,'vie':4,'sab':5,'dom':6}
    _norm = []
    for w in _wds:
        if isinstance(w, int):
            _norm.append(w)
        else:
            try:
                _norm.append(int(w))
            except Exception:
                v = _map.get(str(w).strip().lower()[:3], None)
                if v is not None:
                    _norm.append(v)
    _at = at_dt or datetime.utcnow().replace(hour=12, minute=0, second=0, microsecond=0)
    if _at.weekday() not in set(_norm):
        dtype = "percent" if rule.get("type") == "percent" else ("amount" if rule.get("type") == "amount" else "none")
        dval  = rule.get("value")
        return {
            "valid": False, "code": code_up, "discount_type": dtype,
            "discount_value": (str(dval) if dval is not None else None),
            "discount_amount": Decimal("0.00"),
            "new_total": amount, "reason": "weekday_not_allowed",
            "usage_remaining": None
        }
# WEEKDAYS_SUPPORT_END

'@
      $wkdIndented = ($funIndent) + ($wkdCore -replace "`n","`n$funIndent")
      $txt = $txt.Insert($insertAt2, $wkdIndented)
      Write-Host "[OK] Soporte 'weekdays' insertado en compute_coupon_result()."
    } else {
      Write-Host "[WARN] No se encontró 'rule = COUPONS.get(...)' en compute_coupon_result()."
    }
  } else {
    Write-Host "[WARN] No se encontró def compute_coupon_result(...)."
  }
} else {
  Write-Host "[SKIP] Soporte 'weekdays' ya presente."
}

# -------------------------------------------------------------------
# Guardar y compilar
# -------------------------------------------------------------------
Set-Content -Path $target -Value $txt -Encoding UTF8

try {
  Compile-File $target
  Write-Host "[OK] Compilación correcta."
} catch {
  Write-Host "[ERR] Compilación falló. Restaurando backup..."
  Copy-Item $bak $target -Force
  throw
}

Write-Host "Listo. Archivo parcheado: $target"
Write-Host "Backup: $bak"
Write-Host "Siguiente paso sugerido:"
Write-Host '  .\B-Start-Server.ps1'
Write-Host '  $b = @{ code="WEEKEND15"; amount=129; weekday="sun" } | ConvertTo-Json'
Write-Host '  Invoke-WebRequest -Uri "http://127.0.0.1:8010/pos/coupon/validate" -Method POST -ContentType "application/json" -Body $b'
Write-Host '  .\.venv\Scripts\pytest -q tests\test_coupon_rules_edges.py::test_time_windows_extra_edges'

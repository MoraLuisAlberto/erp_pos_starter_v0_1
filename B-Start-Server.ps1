param(
  [string]$ProjectRoot = "C:\Proyectos\erp-pos\erp_pos_starter_v0_1",
  [int]$Port
)

# Si no llega puerto, usa el de entorno o 8010
if (-not $Port) { $Port = ($env:ERP_POS_PORT) -as [int] }
if (-not $Port) { $Port = 8010 }

# Ir a la raíz y activar venv
Set-Location $ProjectRoot
. .\.venv\Scripts\Activate.ps1

# Asegurar rutas/flags
$env:PYTHONPATH = (Get-Location).Path
if (-not $env:POS_STOCK_POLICY) { $env:POS_STOCK_POLICY = "bypass" }

Write-Host "Iniciando Uvicorn en http://127.0.0.1:$Port (Ctrl+C para detener)..."
python -m uvicorn --app-dir . app.main:app --host 127.0.0.1 --port $Port --reload

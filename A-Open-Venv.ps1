param(
  [string]$ProjectRoot = "C:\Proyectos\erp-pos\erp_pos_starter_v0_1",
  [int]$Port = 8010
)

# Ir a la raíz del proyecto
Set-Location $ProjectRoot

# Activar venv
if (-not (Test-Path .\.venv\Scripts\Activate.ps1)) {
  Write-Error "No encuentro .\.venv\Scripts\Activate.ps1. Crea el venv primero."
  exit 1
}
. .\.venv\Scripts\Activate.ps1

# Variables de entorno necesarias
$env:PYTHONPATH = (Get-Location).Path
$env:POS_STOCK_POLICY = "bypass"      # V1: vender sin control de inventario
$env:ERP_POS_PORT    = $Port

Write-Host "VENV OK. PYTHONPATH =" $env:PYTHONPATH " PORT =" $env:ERP_POS_PORT
python -c "import sys; print('Python',sys.version.split()[0])"

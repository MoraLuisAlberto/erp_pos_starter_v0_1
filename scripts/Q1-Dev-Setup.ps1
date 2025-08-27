param()

Write-Host "== Q1: Dev Tooling Setup =="

# 1) requirements-dev.txt
@"
black==24.4.2
ruff==0.5.6
mypy==1.10.0
pytest==8.2.0
types-requests==2.32.0.20240622
"@ | Set-Content -Encoding UTF8 .\requirements-dev.txt

# 2) pyproject.toml (config de black/ruff/mypy)
@"
[tool.black]
line-length = 100
target-version = ["py312"]

[tool.ruff]
line-length = 100
select = ["E","F","I","UP","B","C4","PIE"]
ignore = ["E501"]  # black maneja long lines

[tool.ruff.isort]
known-first-party = ["app"]
force-sort-within-sections = true

[tool.mypy]
python_version = "3.12"
warn_unused_ignores = true
warn_redundant_casts = true
ignore_missing_imports = true
no_implicit_optional = true
strict_optional = true
"@ | Set-Content -Encoding UTF8 .\pyproject.toml

# 3) pytest.ini (ya lo tienes, aseguramos la advertencia)
if (-not (Test-Path .\pytest.ini)) {
@"
[pytest]
filterwarnings =
    ignore:datetime\.datetime\.utcnow\(\) is deprecated:DeprecationWarning
"@ | Set-Content -Encoding UTF8 .\pytest.ini
}

# 4) .gitignore (añadir cosas comunes)
$giPath = ".\.gitignore"
$giAppend = @"
.venv/
__pycache__/
*.pyc
data/*.json
data/*.jsonl
.pytest_cache/
.mypy_cache/
ruff_cache/
"@
if (Test-Path $giPath) {
  Add-Content -Encoding UTF8 $giPath $giAppend
} else {
  $giAppend | Set-Content -Encoding UTF8 $giPath
}

# 5) Instalar dev deps
& .\.venv\Scripts\python -m pip install -r .\requirements-dev.txt

Write-Host "== Q1 listo =="
Write-Host "Sugeridos:"
Write-Host "  - Formatear: .\.venv\Scripts\python -m black app tests"
Write-Host "  - Lint:      .\.venv\Scripts\python -m ruff check app tests"
Write-Host "  - Tipos:     .\.venv\Scripts\python -m mypy app"
Write-Host "  - Tests:     .\.venv\Scripts\pytest -q"

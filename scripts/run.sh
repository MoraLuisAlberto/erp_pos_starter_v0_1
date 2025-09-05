#!/usr/bin/env bash
set -euo pipefail
# Carga .env si existe
[ -f .env ] && set -a && source .env && set +a
export PYTHONPATH=${PYTHONPATH:-.}
export DATABASE_URL=${DATABASE_URL:-sqlite:///./erp.db}
host="${HOST:-127.0.0.1}"
port="${PORT:-8010}"
exec python -m uvicorn app.main:app --host "$host" --port "$port" --reload

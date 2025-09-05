#!/usr/bin/env bash
set -euo pipefail
v="${1:-}"
if [[ -z "$v" ]]; then
  echo "Uso: ./scripts/release.sh vX.Y.Z" >&2
  exit 1
fi

# Asegura que estás sobre main y al día
git fetch origin --tags
git switch main
git pull --ff-only origin main

# Crea y publica el tag
git tag -a "$v" -m "Release $v"
git push origin "$v"

echo "✅ Tag $v publicado. Si quieres un Release con notas:"
echo "  GitHub → Releases → 'Draft a new release' → selecciona el tag $v y publica."

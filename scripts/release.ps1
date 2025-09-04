# scripts/release.ps1
# Requisitos: gh CLI logueado (gh auth login), estar en Windows PowerShell 5.1+ o PowerShell 7+

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# --- Config ---
$repo = "MoraLuisAlberto/erp_pos_starter_v0_1"

# --- Prechequeos ---
# 1) Verifica gh
try {
  & gh --version | Out-Null
} catch {
  throw "No encuentro 'gh'. Abre una nueva consola o instala GH CLI y ejecuta: gh auth login"
}

# 2) Rama actual debe ser main
$branch = (git branch --show-current).Trim()
if ($branch -ne "main") {
  throw "Cámbiate a la rama 'main' primero (git switch main). Rama actual: $branch"
}

# 3) FF a main
git fetch origin
git pull --ff-only origin main

# 4) Working tree limpio
$dirty = git status --porcelain
if ($dirty) {
  throw "Tienes cambios sin commit. Haz commit/stash antes de continuar."
}

# --- Pide versión ---
$version = Read-Host "Versión a publicar (ej. v0.1.0 o 0.1.0)"
if (-not $version) { throw "Versión vacía." }
if (-not $version.StartsWith("v")) { $version = "v$version" }

# 5) Validar existencia previa del tag/release
$tagExists = $false
try {
  git rev-parse -q --verify "refs/tags/$version" | Out-Null
  $tagExists = $true
} catch { $tagExists = $false }

if ($tagExists) { throw "El tag $version ya existe localmente." }

# 6) Crear tag anotado y empujar
git tag -a $version -m "Release $version"
git push origin $version

# 7) Crear Release con notas auto-generadas
#    (usa Conventional Commits para agrupar por feat/fix/chore, etc.)
& gh release create $version --repo $repo --generate-notes --latest

Write-Host "`n✅ Release $version publicado en GitHub." -ForegroundColor Green

# --- OPCIONAL: sincronizar develop con main (avanza develop si hace falta) ---
try {
  git switch develop
  git pull --ff-only origin develop
  # Intenta fast-forward desde main remoto
  git merge --ff-only origin/main
  git push origin develop
  git switch main
  Write-Host "🔄 'develop' sincronizado con 'main' (fast-forward)." -ForegroundColor Yellow
} catch {
  Write-Host "ℹ️ No se pudo fast-forward 'develop' (quizá ya está al día o hay divergencias). Revisa si lo necesitas." -ForegroundColor DarkYellow
  git switch main
}

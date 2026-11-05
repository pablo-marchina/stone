# Run against a CLEAN repository with real Git remote access on Windows.
# Creates a detached, temporary worktree; does not mutate main or the live SQLite.
param(
  [Parameter(Mandatory=$true)][string]$E7Patch,
  [Parameter(Mandatory=$true)][string]$E8Patch
)
$ErrorActionPreference = 'Stop'
function Assert-Native { if ($LASTEXITCODE -ne 0) { throw "Comando nativo falhou: $LASTEXITCODE" } }
$expected37='e237ce426bf59cf22979528172cbaf8cdfeaad33'
$expected38='f018e3f18faac97233416cbb354e554ba7ce7a4f'
$expected39='719d66ca0b2f424f17f677a781021baf2a57a0e8'
if (!(Test-Path $E7Patch) -or !(Test-Path $E8Patch)) { throw 'Informe caminhos válidos para os patches E7 e E8.' }
# git status may be nonclean; the worktree is independent and does not reset files.
git fetch origin; Assert-Native
$heads=@{
  'feat/imp182-183-studio-versioned-carousel-20261105'=$expected37;
  'feat/cap023-e4-e5-version-export-storyboard-20261105'=$expected38;
  'feat/cap023-e6-offline-render-rights-evidence-20261105'=$expected39
}
foreach ($branch in $heads.Keys) {
  $current=(git rev-parse "origin/$branch").Trim(); Assert-Native
  if ($current -ne $heads[$branch]) { throw "HEAD de $branch mudou; reconcilie antes de executar: $current" }
  Write-Output "SHA validado: $branch = $current"
}
$worktree=Join-Path ([System.IO.Path]::GetTempPath()) ('stone-e8-exact-'+[guid]::NewGuid().ToString('N').Substring(0,12))
git worktree add --detach $worktree $expected39; Assert-Native
Write-Output "Worktree exato: $worktree"
Push-Location $worktree
try {
  $env:PYTHONPATH=(Resolve-Path '.\src').Path
  $db=(Join-Path $worktree 'e8-validation.sqlite3').Replace('\','/')
  $env:TAPI_DATABASE_URL="sqlite:///$db"
  # Never use the operator's live database, token or Meta flags.
  Remove-Item Env:TAPI_INSTAGRAM_ACCESS_TOKEN -ErrorAction SilentlyContinue
  Remove-Item Env:TAPI_META_ACCESS_TOKEN -ErrorAction SilentlyContinue
  Remove-Item Env:TAPI_OFFICIAL_METADATA_READS -ErrorAction SilentlyContinue
  Remove-Item Env:TAPI_BD_TECHNICAL_INGEST -ErrorAction SilentlyContinue
  Write-Output '### Base PR39: validar HEAD exato antes dos patches'
  python -m pytest -q; Assert-Native
  python scripts/check_gate0.py; Assert-Native
  python scripts/verify_zero_spend.py; Assert-Native
  node --test tests/frontend/test_events.mjs; Assert-Native
  Write-Output '### E7: aplicar sobre PR39 com checagem'
  git apply --check (Resolve-Path $E7Patch); Assert-Native
  git apply (Resolve-Path $E7Patch); Assert-Native
  Write-Output '### E8: aplicar depois de E7 com checagem'
  git apply --check (Resolve-Path $E8Patch); Assert-Native
  git apply (Resolve-Path $E8Patch); Assert-Native
  python -m alembic upgrade head; Assert-Native
  python -m pytest -q; Assert-Native
  node --check src/tapi_gate0/web/studio.mjs; Assert-Native
  node --check src/tapi_gate0/web/studio_timeline_e8.js; Assert-Native
  node --test tests/frontend/test_events.mjs tests/frontend/test_studio_timeline_e8.mjs; Assert-Native
  # These flags are for an isolated local-only QA fixture, never the live environment.
  $env:TAPI_LOCAL_RENDER_ENABLED='1'
  $env:TAPI_ZERO_BILLING_CONFIRMED='1'
  $env:TAPI_E7_VIDEO_RENDER_ENABLED='1'
  try { python scripts/e8_chromium_timeline_qa.py; Assert-Native }
  finally {
    Remove-Item Env:TAPI_LOCAL_RENDER_ENABLED -ErrorAction SilentlyContinue
    Remove-Item Env:TAPI_ZERO_BILLING_CONFIRMED -ErrorAction SilentlyContinue
    Remove-Item Env:TAPI_E7_VIDEO_RENDER_ENABLED -ErrorAction SilentlyContinue
  }
  python scripts/check_gate0.py; Assert-Native
  python scripts/verify_zero_spend.py; Assert-Native
  git diff --check; Assert-Native
  Write-Output 'VALIDACAO E8 CONCLUIDA NO BASE SHA PR39 EXATO + PATCHES E7/E8; nenhuma integracao automatica.'
  git status --short
}
finally {
  Pop-Location
  Write-Output "O worktree temporário foi preservado para auditoria: $worktree"
}

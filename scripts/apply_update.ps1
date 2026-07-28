#Requires -Version 5.1
<#
.SYNOPSIS
  Apply an update zip/folder onto an installed SAA Alpha tree WITHOUT overwriting data\.

.EXAMPLE
  powershell -File scripts\apply_update.ps1 -ZipPath .\saa-alpha-update.zip
  powershell -File scripts\apply_update.ps1 -SourceDir .\dist\SAA-Alpha-portable
#>
param(
  [string]$InstallRoot = "",
  [string]$ZipPath = "",
  [string]$SourceDir = "",
  [switch]$AlsoRefreshVenv
)

$ErrorActionPreference = "Stop"
if (-not $InstallRoot) {
  $InstallRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
}

Write-Host "[update] install=$InstallRoot"

if (-not $SourceDir) {
  if (-not $ZipPath) {
    $candidates = @(
      (Join-Path $InstallRoot "saa-alpha-update.zip"),
      (Join-Path $InstallRoot "dist\SAA-Alpha-portable.zip"),
      (Join-Path (Split-Path $InstallRoot -Parent) "saa-alpha-update.zip")
    )
    $ZipPath = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
  }
  if (-not $ZipPath -or -not (Test-Path $ZipPath)) {
    throw "No update zip. Pass -ZipPath or place saa-alpha-update.zip next to the app."
  }
  $stage = Join-Path $env:TEMP ("saa_update_" + [guid]::NewGuid().ToString("N"))
  New-Item -ItemType Directory -Force -Path $stage | Out-Null
  Write-Host "[update] extract $ZipPath -> $stage"
  Expand-Archive -LiteralPath $ZipPath -DestinationPath $stage -Force
  # If zip contains a single top folder, descend into it
  $kids = Get-ChildItem $stage | Where-Object { $_.Name -notmatch '^\.' }
  if ($kids.Count -eq 1 -and $kids[0].PSIsContainer) {
    $SourceDir = $kids[0].FullName
  } else {
    $SourceDir = $stage
  }
}

if (-not (Test-Path $SourceDir)) { throw "SourceDir missing: $SourceDir" }

# Safety backup of ledger before merge
$bak = Join-Path $InstallRoot ("data\local\backups\pre_update_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
New-Item -ItemType Directory -Force -Path $bak | Out-Null
foreach ($rel in @(
  "data\positions.csv",
  "data\target_portfolio.csv",
  "data\kr_alpha_exit_targets.yaml",
  "data\alpha_dashboard_runtime.json",
  "data\weekly_qual_suggestions.json",
  "data\monthly_cecs_suggestions.json"
)) {
  $p = Join-Path $InstallRoot $rel
  if (Test-Path $p) {
    $dest = Join-Path $bak (Split-Path $rel -Leaf)
    Copy-Item $p $dest -Force
  }
}
Write-Host "[update] ledger snapshot -> $bak"

# Copy everything EXCEPT data\ (and never wipe user's data)
$exclude = @("data", ".git")
& robocopy $SourceDir $InstallRoot /E /XO /NFL /NDL /NJH /NJS /nc /ns /np `
  /XD data .git `
  /XF "positions.csv" | Out-Null
if ($LASTEXITCODE -ge 8) { throw "robocopy update failed code=$LASTEXITCODE" }

# Seed any NEW data files that user does not have yet (never overwrite)
$dataSrc = Join-Path $SourceDir "data"
$dataDst = Join-Path $InstallRoot "data"
if (Test-Path $dataSrc) {
  Get-ChildItem $dataSrc -Recurse -File | ForEach-Object {
    $rel = $_.FullName.Substring($dataSrc.Length).TrimStart("\", "/")
    # skip regenerable / local
    if ($rel -match '^(cache\\|local\\|prices_history)') { return }
    $target = Join-Path $dataDst $rel
    if (-not (Test-Path $target)) {
      $parent = Split-Path $target -Parent
      if (-not (Test-Path $parent)) { New-Item -ItemType Directory -Force -Path $parent | Out-Null }
      Copy-Item $_.FullName $target -Force
      Write-Host "[update] seeded data\$rel"
    }
  }
}

if ($AlsoRefreshVenv) {
  $srcVenv = Join-Path $SourceDir ".venv"
  if (Test-Path $srcVenv) {
    Write-Host "[update] refreshing .venv from package ..."
    $dstVenv = Join-Path $InstallRoot ".venv"
    if (Test-Path $dstVenv) { Remove-Item -Recurse -Force $dstVenv }
    & robocopy $srcVenv $dstVenv /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "venv refresh failed" }
  }
}

@"
updated=$(Get-Date -Format 'o')
source=$SourceDir
zip=$ZipPath
"@ | Set-Content -Encoding utf8 (Join-Path $InstallRoot "LAST_UPDATE.txt")

Write-Host "[update] OK — data\ preserved. Restart 투자나침반.bat"
exit 0

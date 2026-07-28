#Requires -Version 5.1
<#
.SYNOPSIS
  Build a portable SAA Alpha folder with a local .venv (no system Python required at runtime).

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\bundle_runtime.ps1
  powershell -ExecutionPolicy Bypass -File scripts\bundle_runtime.ps1 -Zip
#>
param(
  [string]$Root = "",
  [string]$OutDir = "",
  [switch]$Zip,
  [switch]$SkipVenv,
  [string]$Python = ""
)

$ErrorActionPreference = "Stop"
if (-not $Root) { $Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path }
if (-not $OutDir) { $OutDir = Join-Path $Root "dist\SAA-Alpha-portable" }

function Find-Python {
  param([string]$Hint)
  if ($Hint -and (Test-Path $Hint)) { return $Hint }
  foreach ($c in @(
    (Join-Path $Root ".venv\Scripts\python.exe"),
    "py",
    "python"
  )) {
    if ($c -eq "py" -or $c -eq "python") {
      $cmd = Get-Command $c -ErrorAction SilentlyContinue
      if ($cmd) { return $c }
    } elseif (Test-Path $c) {
      return $c
    }
  }
  throw "Python 3.11+ not found. Install Python or pass -Python path."
}

Write-Host "[bundle] root=$Root"
Write-Host "[bundle] out =$OutDir"

$pyForCreate = Find-Python -Hint $Python
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"

if (-not $SkipVenv) {
  if (-not (Test-Path $venvPy)) {
    Write-Host "[bundle] creating .venv ..."
    if ($pyForCreate -eq "py") {
      & py -3.11 -m venv (Join-Path $Root ".venv")
      if ($LASTEXITCODE -ne 0) { & py -3 -m venv (Join-Path $Root ".venv") }
    } else {
      & $pyForCreate -m venv (Join-Path $Root ".venv")
    }
    if (-not (Test-Path $venvPy)) { throw "venv create failed" }
  }
  Write-Host "[bundle] pip install -e .[ui,data] ..."
  & $venvPy -m pip install --upgrade pip
  Push-Location $Root
  try {
    & $venvPy -m pip install -e ".[ui,data]"
    if ($LASTEXITCODE -ne 0) { throw "pip install failed" }
  } finally {
    Pop-Location
  }
}

# Fresh portable tree
if (Test-Path $OutDir) { Remove-Item -Recurse -Force $OutDir }
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null

$excludeDirs = @(
  ".git", ".cursor", ".pytest_cache", "__pycache__", "agent-transcripts",
  "outputs", "dist", "archive", "htmlcov", ".mypy_cache", ".ruff_cache",
  "docs\archive"
)

# Copy repo (code + tracked data seed) excluding noise
$robolog = Join-Path $env:TEMP "saa_bundle_robo.log"
$xd = @()
foreach ($d in $excludeDirs) { $xd += @("/XD", $d) }
# Exclude regenerable / local-heavy data under data\
$xd += @("/XD", "cache", "local", "backups", "quarantine")

& robocopy $Root $OutDir /E /NFL /NDL /NJH /NJS /nc /ns /np `
  /XF "*.pyc" "*.pyo" ".coverage" "prices_history.csv" "prices_history_*.csv" `
  @xd | Out-Null
# robocopy exit 0-7 = success-ish
if ($LASTEXITCODE -ge 8) { throw "robocopy failed code=$LASTEXITCODE" }

# Ensure bundled venv is inside portable (copy from root .venv)
$srcVenv = Join-Path $Root ".venv"
$dstVenv = Join-Path $OutDir ".venv"
if (Test-Path $srcVenv) {
  Write-Host "[bundle] copying .venv (large) ..."
  if (Test-Path $dstVenv) { Remove-Item -Recurse -Force $dstVenv }
  & robocopy $srcVenv $dstVenv /E /NFL /NDL /NJH /NJS /nc /ns /np | Out-Null
  if ($LASTEXITCODE -ge 8) { throw "venv robocopy failed" }
} else {
  Write-Host "[bundle] WARN: no .venv — portable will need system Python"
}

# Do not ship developer chat noise
$stubData = Join-Path $OutDir "data"
New-Item -ItemType Directory -Force -Path (Join-Path $stubData "local\backups") | Out-Null

# Marker
@"
SAA Alpha portable build
built=$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
root_source=$Root
"@ | Set-Content -Encoding utf8 (Join-Path $OutDir "PACKAGED.txt")

Copy-Item (Join-Path $Root "docs\V3_WINDOWS_PACKAGING.md") (Join-Path $OutDir "설치·업데이트안내.md") -ErrorAction SilentlyContinue

Write-Host "[bundle] done: $OutDir"
if ($Zip) {
  $zipPath = Join-Path $Root ("dist\SAA-Alpha-portable-{0}.zip" -f (Get-Date -Format "yyyyMMdd"))
  if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
  Write-Host "[bundle] zipping $zipPath ..."
  Compress-Archive -Path (Join-Path $OutDir "*") -DestinationPath $zipPath -CompressionLevel Optimal
  Write-Host "[bundle] zip=$zipPath"
}

Write-Host "[bundle] Next: open packaging\saa_alpha.iss in Inno Setup (SourceDir = dist\SAA-Alpha-portable)"
exit 0

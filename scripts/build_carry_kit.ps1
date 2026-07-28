#Requires -Version 5.1
<#
.SYNOPSIS
  Build the two-piece carry kit: App + Backup.

  dist\CARRY\
    01_SAA-Alpha-App\     program (portable) or placeholder
    02_SAA-Alpha-Backup\  ledger export
    README_CARRY.txt

.EXAMPLE
  powershell -File scripts\build_carry_kit.ps1
  powershell -File scripts\build_carry_kit.ps1 -Bundle
#>
param(
  [switch]$Bundle,
  [switch]$WithSecrets
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Carry = Join-Path $Root "dist\CARRY"
$App = Join-Path $Carry "01_SAA-Alpha-App"
$Backup = Join-Path $Carry "02_SAA-Alpha-Backup"
$utf8 = New-Object System.Text.UTF8Encoding $false

function Write-Utf8File([string]$Path, [string]$Text) {
  [System.IO.File]::WriteAllText($Path, $Text, $utf8)
}

Write-Host "[carry] root=$Root"
New-Item -ItemType Directory -Force -Path $Carry | Out-Null

# Icon
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
$iconScript = Join-Path $Root "scripts\build_app_icon.py"
if (Test-Path $venvPy) { & $venvPy $iconScript } else { python $iconScript }
if ($LASTEXITCODE -ne 0) { throw "build_app_icon failed" }

if ($Bundle) {
  Write-Host "[carry] bundling portable app (slow)..."
  powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $Root "scripts\bundle_runtime.ps1")
  $portable = Join-Path $Root "dist\SAA-Alpha-portable"
  if (-not (Test-Path $portable)) { throw "portable missing" }
  if (Test-Path $App) { Remove-Item -Recurse -Force $App }
  Move-Item $portable $App
} else {
  New-Item -ItemType Directory -Force -Path $App | Out-Null
  $hint = @"
This folder is for the PROGRAM (half #1).

Build full portable:
  powershell -File scripts\build_carry_kit.ps1 -Bundle

Or compile Setup.exe:
  packaging\saa_alpha.iss (Inno Setup)

Icon: saa_alpha.ico
Run: 투자나침반.bat / SAA_Alpha.lnk
"@
  Write-Utf8File (Join-Path $App "PUT_APP_HERE.txt") $hint
  $srcIco = Join-Path $Root "saa_alpha.ico"
  if (Test-Path $srcIco) { Copy-Item $srcIco (Join-Path $App "saa_alpha.ico") -Force }
}

function New-AppShortcut([string]$LnkPath, [string]$TargetBat, [string]$WorkDir, [string]$IcoPath) {
  $w = New-Object -ComObject WScript.Shell
  $s = $w.CreateShortcut($LnkPath)
  $s.TargetPath = $TargetBat
  $s.WorkingDirectory = $WorkDir
  $s.WindowStyle = 7
  if (Test-Path $IcoPath) { $s.IconLocation = "$IcoPath,0" }
  $s.Description = "SAA Alpha Ops Assistant"
  $s.Save()
}

$icoRoot = Join-Path $Root "saa_alpha.ico"
$batApp = Join-Path $App "Launch_SAA.bat"
if (-not (Test-Path $batApp)) { $batApp = Join-Path $App "run_ui_direct.bat" }
$icoApp = Join-Path $App "saa_alpha.ico"
if (-not (Test-Path $icoApp)) { $icoApp = $icoRoot }
if (Test-Path $batApp) {
  New-AppShortcut (Join-Path $App "SAA_Alpha.lnk") $batApp $App $icoApp
}

$rootBat = Join-Path $Root "Launch_SAA.bat"
if (Test-Path $rootBat) {
  New-AppShortcut (Join-Path $Root "SAA_Alpha.lnk") $rootBat $Root $icoRoot
}

$py = if (Test-Path $venvPy) { $venvPy } else { "python" }
$exportArgs = @((Join-Path $Root "scripts\export_ledger.py"), "--root", $Root, "--out", $Backup)
if ($WithSecrets) { $exportArgs += "--with-secrets" }
& $py @exportArgs
if ($LASTEXITCODE -ne 0) { throw "export_ledger failed" }

$guide = @"
========================================
  SAA Alpha — carry only these TWO
========================================

(1) 01_SAA-Alpha-App     = program  (or Setup.exe)
(2) 02_SAA-Alpha-Backup  = ledger   (holdings / targets / approvals)

New PC:
  1. Install/copy (1), run 투자나침반 or SAA_Alpha icon
  2. Run 장부_가져오기.bat and point to (2)

Refresh ledger only:
  장부_내보내기.bat  -> updates folder (2)

Not auto-trading. Review-only.
Docs: docs\V3_CARRY_KIT.md
"@
Write-Utf8File (Join-Path $Carry "README_CARRY.txt") $guide

Write-Host "[carry] done -> $Carry"
try { explorer $Carry } catch {}
exit 0

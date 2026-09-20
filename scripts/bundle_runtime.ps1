#Requires -Version 5.1
<#
.SYNOPSIS
  Wrapper — secret-free portable pack (see scripts/pack_portable.py).
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\bundle_runtime.ps1 -Zip
#>
param(
  [switch]$Zip,
  [switch]$SkipPython
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $py)) { $py = "python" }
$packArgs = @((Join-Path $Root "scripts\pack_portable.py"))
if ($SkipPython) { $packArgs += "--skip-python" }
if ($Zip) { $packArgs += "--zip" }
& $py @packArgs
exit $LASTEXITCODE

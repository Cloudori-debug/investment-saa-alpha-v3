# P4c smoke tier — target <= 5 minutes
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

python scripts/run_test_tier.py smoke
exit $LASTEXITCODE

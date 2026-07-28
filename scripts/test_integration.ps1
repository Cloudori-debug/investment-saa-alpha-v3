# P4c integration tier — target <= 60 minutes
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

python scripts/run_test_tier.py integration
exit $LASTEXITCODE

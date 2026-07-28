# P4c fast tier — target <= 20 minutes
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

python scripts/run_test_tier.py fast --append
exit $LASTEXITCODE

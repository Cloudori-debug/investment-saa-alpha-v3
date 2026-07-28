# P4c deep tier — manual / long-running (network, pykrx, external_data)
Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

python scripts/run_test_tier.py deep
exit $LASTEXITCODE

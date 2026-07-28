# 일일 파이프라인 — Windows 작업 스케줄러 등록 (평일 08:00 KST)
# 관리자 권한 불필요. 한 번만 실행하세요.
# 제거: Unregister-ScheduledTask -TaskName "MultiAssetDailyPipeline" -Confirm:$false

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) {
    Write-Error "python not found in PATH"
}

$Action = New-ScheduledTaskAction `
    -Execute $Python `
    -Argument "scripts\daily_pipeline.py --no-backtest" `
    -WorkingDirectory $Root

$Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 8:00AM

$Settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2)

Register-ScheduledTask `
    -TaskName "MultiAssetDailyPipeline" `
    -Action $Action `
    -Trigger $Trigger `
    -Settings $Settings `
    -Description "투자 나침반: 시장지표 갱신 + 전체 분석 + dry-run 로그" `
    -Force | Out-Null

Write-Host "등록 완료: MultiAssetDailyPipeline (평일 08:00)"
Write-Host "수동 테스트: cd $Root; python scripts\daily_pipeline.py --no-backtest"

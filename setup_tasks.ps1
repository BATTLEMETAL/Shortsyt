# setup_tasks.ps1
# Uruchom JAKO ADMINISTRATOR: Prawy click -> "Uruchom jako administrator"
# Rejestruje 2 zadania Windows Task Scheduler:
#   1. ShortsytDaily  - codziennie o 10:00
#   2. ShortsytWeekly - co poniedzialek o 09:00 (analiza kanalu)

$ProjectDir = "c:\Users\mz100\PycharmProjects\shortsyt"
$PythonExe  = "$ProjectDir\venv313\Scripts\python.exe"
$DailyBat   = "$ProjectDir\start_daily.bat"
$WeeklyPy   = "$ProjectDir\weekly_channel_analyzer.py"
$LogDir     = "$ProjectDir\logs"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir | Out-Null }

Write-Host "" 
Write-Host "=== SHORTSYT - Windows Task Scheduler Setup ===" -ForegroundColor Cyan
Write-Host ""

# ── TASK 1: Codzienne shortsy o 10:00 ─────────────────────────
$TaskName1 = "ShortsytDaily"
if (Get-ScheduledTask -TaskName $TaskName1 -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName1 -Confirm:$false
    Write-Host "[INFO] Stare zadanie '$TaskName1' usunieto." -ForegroundColor Yellow
}

$Action1   = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"$DailyBat`" >> `"$LogDir\daily.log`" 2>&1"
$Trigger1  = New-ScheduledTaskTrigger -Daily -At "10:00"
$Settings1 = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -WakeToRun:$false

Register-ScheduledTask `
    -TaskName    $TaskName1 `
    -Action      $Action1 `
    -Trigger     $Trigger1 `
    -Settings    $Settings1 `
    -RunLevel    Highest `
    -Description "Shortsyt: 2 Dark Psychology shorts dziennie o 10:00" | Out-Null

Write-Host "[OK] '$TaskName1' -> codziennie o 10:00" -ForegroundColor Green

# ── TASK 2: Tygodniowa analiza kanaalu (poniedzialek 09:00) ───
$TaskName2 = "ShortsytWeekly"
if (Get-ScheduledTask -TaskName $TaskName2 -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName2 -Confirm:$false
    Write-Host "[INFO] Stare zadanie '$TaskName2' usunieto." -ForegroundColor Yellow
}

$Action2   = New-ScheduledTaskAction `
    -Execute $PythonExe `
    -Argument "weekly_channel_analyzer.py" `
    -WorkingDirectory $ProjectDir
$Trigger2  = New-ScheduledTaskTrigger `
    -Weekly -WeeksInterval 1 -DaysOfWeek Monday -At "09:00"
$Settings2 = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

$Env2 = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -RunLevel Highest

Register-ScheduledTask `
    -TaskName    $TaskName2 `
    -Action      $Action2 `
    -Trigger     $Trigger2 `
    -Settings    $Settings2 `
    -Principal   $Env2 `
    -Description "Shortsyt: tygodniowa analiza kanalu YT co poniedzialek 09:00" | Out-Null

Write-Host "[OK] '$TaskName2' -> kazdy poniedzialek o 09:00" -ForegroundColor Green

Write-Host ""
Write-Host "=== GOTOWE ===" -ForegroundColor Cyan
Write-Host "Sprwadz zadania w: taskschd.msc" -ForegroundColor Yellow
Write-Host "Uruchom recznie:   Start-ScheduledTask -TaskName 'ShortsytDaily'" -ForegroundColor Yellow
Write-Host ""
Write-Host "Logi beda w: $LogDir\daily.log"
Write-Host ""
Write-Host "Nacisnij Enter aby zamknac..."
Read-Host

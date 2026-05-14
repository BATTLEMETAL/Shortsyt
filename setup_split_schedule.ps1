$dir = "c:\Users\mz100\PycharmProjects\shortsyt"
$logDir = $dir + "\logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

$tasks = "ShortsytDaily", "YouTubeShortsDailyAuto", "ShortsytMorning", "ShortsytEvening"
foreach ($t in $tasks) {
    if (Get-ScheduledTask -TaskName $t -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $t -Confirm:$false
        Write-Host ("[USUNIETO] " + $t)
    }
}

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

$morningArg = "/c `"" + $dir + "\start_morning.bat`" >> `"" + $logDir + "\morning.log`" 2>&1"
$a1 = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $morningArg -WorkingDirectory $dir
$t1 = New-ScheduledTaskTrigger -Daily -At "14:00"
Register-ScheduledTask -TaskName "ShortsytMorning" -Action $a1 -Trigger $t1 -Settings $settings -RunLevel Highest -Force | Out-Null
Write-Host "[OK] ShortsytMorning  - 14:00 PL (Film 1 - popoldnie)"

$eveningArg = "/c `"" + $dir + "\start_evening.bat`" >> `"" + $logDir + "\evening.log`" 2>&1"
$a2 = New-ScheduledTaskAction -Execute "cmd.exe" -Argument $eveningArg -WorkingDirectory $dir
$t2 = New-ScheduledTaskTrigger -Daily -At "19:00"
Register-ScheduledTask -TaskName "ShortsytEvening" -Action $a2 -Trigger $t2 -Settings $settings -RunLevel Highest -Force | Out-Null
Write-Host "[OK] ShortsytEvening  - 19:00 PL (Film 2 - wieczor)"

Write-Host ""
Write-Host "=== AKTYWNE ZADANIA ==="
Get-ScheduledTask | Where-Object { $_.TaskName -like "Shortsyt*" } | Select-Object TaskName, State | Format-Table -AutoSize

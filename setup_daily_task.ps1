$taskName = "YouTubeShortsDailyAuto"
$actionScript = "C:\Users\mz100\PycharmProjects\shortsyt\start_daily.bat"
$workingDir = "C:\Users\mz100\PycharmProjects\shortsyt"

Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue

$trigger = New-ScheduledTaskTrigger -Daily -At 10:00PM

# Używamy ścieżki bezpośredniej do bat jako komendy
$action = New-ScheduledTaskAction -Execute $actionScript -WorkingDirectory $workingDir

$principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RunOnlyIfNetworkAvailable

$task = New-ScheduledTask -Action $action -Principal $principal -Trigger $trigger -Settings $settings

Register-ScheduledTask -TaskName $taskName -InputObject $task

Write-Host "✅ Pomyślnie dodano zadanie do Harmonogramu Zadań Windows."
Write-Host "🕒 Skrypt będzie uruchamiał się codziennie o 22:00 PL i generował 2 shortsy (peak: 14:00, 19:00 PL na jutro)."


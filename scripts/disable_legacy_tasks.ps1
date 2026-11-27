#Requires -RunAsAdministrator
<#
.SYNOPSIS
Wyłącza 3 stare zadania legacy ze starego repozytorium (PycharmProjects\shortsyt),
które mają RunLevel=Highest i wymagają uprawnień Administratora (UAC).

Uruchomienie (PowerShell jako Administrator):
  powershell -ExecutionPolicy Bypass -File "C:\Users\mz100\OneDrive\Michal\Shortsyt\scripts\disable_legacy_tasks.ps1"
#>

$ErrorActionPreference = "Stop"
$legacyTasks = @("ShortsytMorning", "ShortsytEvening", "ShortsytWeekly")

foreach ($taskName in $legacyTasks) {
    $t = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if (-not $t) {
        Write-Output "[SKIP] Zadanie nie istnieje: $taskName"
        continue
    }
    if ($t.State -eq "Disabled") {
        Write-Output "[OK] Już wyłączone: $taskName"
        continue
    }
    Disable-ScheduledTask -TaskName $taskName | Out-Null
    Write-Output "[DISABLED] Wyłączono stare zadanie: $taskName"
}

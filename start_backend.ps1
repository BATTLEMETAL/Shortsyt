# Flikcut Backend Auto-Start
# Task Scheduler uruchamia ten plik przy logowaniu
# PowerShell wrapper — identyczne srodowisko jak reczne uruchomienie

Set-Location "C:\Users\mz100\OneDrive\Michal\Shortsyt"

# Poczekaj az OneDrive zamontuje (max 15s)
$waited = 0
while (-not (Test-Path "C:\Users\mz100\OneDrive\Michal\Shortsyt\lol_agent") -and $waited -lt 15) {
    Start-Sleep -Seconds 1
    $waited++
}

# Sprawdz czy port juz zajety
$listening = netstat -ano | Select-String "127.0.0.1:8765.*LISTENING"
if ($listening) {
    Write-Output "[Flikcut] Backend already running on 8765 - skip"
    exit 0
}

Write-Output "[Flikcut] Starting backend on 127.0.0.1:8765..."

# Uruchom uvicorn — blokuje do zamkniecia (Task Scheduler widzi ze task zyje)
& ".\venv313\Scripts\python.exe" -m uvicorn lol_agent.api.main:app `
    --host 127.0.0.1 `
    --port 8765 `
    --log-level warning *>> "$env:TEMP\flikcut_backend.log"

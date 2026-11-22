@echo off
:: Flikcut Backend Auto-Start
:: Uruchamia FastAPI na 127.0.0.1:8765

:: Ustaw working directory absolutnie
cd /d "C:\Users\mz100\OneDrive\Michal\Shortsyt"

:: Poczekaj 8s na OneDrive sync przy starcie
timeout /t 8 /nobreak >nul

:: Sprawdz czy port juz zajety
netstat -an | findstr "127.0.0.1:8765" | findstr "LISTENING" >nul 2>&1
if %errorlevel% == 0 (
    echo [Flikcut] Backend already running - skip
    exit /b 0
)

:: Uruchom backend — log do %TEMP%
"C:\Users\mz100\OneDrive\Michal\Shortsyt\venv313\Scripts\python.exe" ^
    -m uvicorn lol_agent.api.main:app ^
    --host 127.0.0.1 ^
    --port 8765 ^
    --log-level warning ^
    >> "%TEMP%\flikcut_backend.log" 2>&1

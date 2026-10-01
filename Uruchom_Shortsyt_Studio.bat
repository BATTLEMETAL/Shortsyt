@echo off
setlocal
chcp 65001 >nul
title Shortsyt Studio Launcher
cd /d "%~dp0"

echo ========================================================
echo        SHORTSYT STUDIO - 1-CLICK LAUNCHER
echo ========================================================
echo.

:: 1. Check if backend is running, start in background if needed
echo [1/2] Sprawdzanie serwera backendu FastAPI (port 8765)...
curl -s --connect-timeout 2 http://127.0.0.1:8765/health >nul 2>&1
if %ERRORLEVEL% EQU 0 goto backend_ready

echo       Uruchamianie serwera FastAPI w tle...
start /min "" ".\venv313\Scripts\python.exe" -m uvicorn lol_agent.api.main:app --host 127.0.0.1 --port 8765

set /a attempts=0
:wait_loop
ping 127.0.0.1 -n 2 >nul
curl -s --connect-timeout 2 http://127.0.0.1:8765/health >nul 2>&1
if %ERRORLEVEL% EQU 0 goto backend_ready
set /a attempts+=1
if %attempts% LSS 10 goto wait_loop
echo       [Ostrzezenie] Serwer moze jeszcze startowac.

:backend_ready
echo       Serwer backendu FastAPI jest aktywny [OK]

:: 2. Launch Shortsyt Studio Desktop Application
echo [2/2] Uruchamianie aplikacji Shortsyt Studio...
if exist "%~dp0shortsyt-desktop\dist-installer\win-unpacked\Shortsyt Studio.exe" (
    start "" /d "%~dp0shortsyt-desktop\dist-installer\win-unpacked" "%~dp0shortsyt-desktop\dist-installer\win-unpacked\Shortsyt Studio.exe"
    echo.
    echo [OK] Shortsyt Studio zostalo pomyslnie uruchomione!
    ping 127.0.0.1 -n 3 >nul
    exit /b 0
)

if exist "%~dp0shortsyt-desktop\node_modules\electron\dist\electron.exe" (
    echo       Uruchamianie wersji deweloperskiej Electron...
    cd /d "%~dp0shortsyt-desktop"
    start "" npm start
    cd /d "%~dp0"
    echo.
    echo [OK] Shortsyt Studio DEV zostalo pomyslnie uruchomione!
    ping 127.0.0.1 -n 3 >nul
    exit /b 0
)

:: Fallback do przegladarki jesli brak Electrona
echo       Otwieranie panelu w przegladarce...
start http://localhost:8765
echo.
echo [OK] Shortsyt Studio otwarte w przegladarce!
ping 127.0.0.1 -n 3 >nul
exit /b 0



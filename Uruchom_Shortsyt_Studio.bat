@echo off
chcp 65001 >nul
title Shortsyt Studio Launcher
cd /d "%~dp0"

echo ========================================================
echo        🚀 SHORTSYT STUDIO — 1-CLICK LAUNCHER
echo ========================================================
echo.

:: 1. Check if backend is running, start in background if needed
curl -s http://127.0.0.1:8765/health >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [1/3] Uruchamianie serwera backendu FastAPI (port 8765)...
    start /min "" ".\venv313\Scripts\python.exe" -m uvicorn lol_agent.api.main:app --host 127.0.0.1 --port 8765
    timeout /t 2 /nobreak >nul
) else (
    echo [1/3] Serwer backendu FastAPI jest aktywny [OK]
)

:: 2. Launch Default Web Browser immediately
echo [2/3] Otwieranie panelu Shortsyt Studio w przegladarce...
start http://localhost:8765

:: 3. Optional: Launch Electron Desktop Window if available
if exist "shortsyt-desktop\release\win-unpacked\Shortsyt Studio.exe" (
    echo [3/3] Uruchamianie dedykowanego okna aplikacji desktopowej...
    start "" "shortsyt-desktop\release\win-unpacked\Shortsyt Studio.exe"
)

echo.
echo ✅ Shortsyt Studio zostalo pomyslnie uruchomione!
timeout /t 2 >nul
exit

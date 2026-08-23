@echo off
chcp 65001 >nul
title Shortsyt API Server

echo.
echo ╔══════════════════════════════════════╗
echo ║       SHORTSYT API SERVER            ║
echo ║       http://localhost:8765          ║
echo ╚══════════════════════════════════════╝
echo.

:: Sprawdź czy cloudflared jest zainstalowany
where cloudflared >nul 2>&1
if %ERRORLEVEL% == 0 (
    echo [OK] cloudflared znaleziony
    echo [INFO] Uruchamiam Cloudflare Tunnel w tle...
    start "Cloudflare Tunnel" cloudflared tunnel run shortsyt
    timeout /t 3 /nobreak >nul
) else (
    echo [WARN] cloudflared nie znaleziony - tylko dostep lokalny
    echo [INFO] Zainstaluj: winget install Cloudflare.cloudflared
)

echo.
echo [INFO] Uruchamiam FastAPI na porcie 8765...
echo [INFO] Dokumentacja API: http://localhost:8765/docs
echo.

:: Uruchom z venv projektu
set PYTHONPATH=%~dp0..\..
set PYTHONIOENCODING=utf-8

..\..\venv313\Scripts\python.exe -m uvicorn lol_agent.api.main:app --host 0.0.0.0 --port 8765 --reload

pause

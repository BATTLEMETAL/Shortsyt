@echo off
chcp 65001 >nul
title Shortsyt Desktop Launcher

echo ╔══════════════════════════════════════════════════════╗
echo ║        SHORTSYT DESKTOP — LoL Shorts Studio          ║
echo ╚══════════════════════════════════════════════════════╝
echo.

cd /d "%~dp0"

echo [1/2] Sprawdzanie serwera backend FastAPI...
powershell -Command "try { $r = Invoke-WebRequest -Uri 'http://localhost:8765/health' -UseBasicParsing -TimeoutSec 2; Write-Host '[OK] Backend FastAPI jest aktywny' -ForegroundColor Green } catch { Write-Host '[INFO] Serwer FastAPI nie jest uruchomiony na porcie 8765 (możesz go odpalić z lol_agent\api\start_server.bat)' -ForegroundColor Yellow }"

echo.
echo [2/2] Uruchamianie aplikacji Electron Desktop...
npm run dev

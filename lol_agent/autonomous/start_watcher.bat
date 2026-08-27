@echo off
title LOL Agent — Autonomous Watcher
cd /d "%~dp0..\.."
echo ========================================================
echo   LOL AGENT — AUTONOMOUS FOLDER WATCHER (Dwannellenga)
echo ========================================================
echo.
echo Monitorowanie folderu nagran Outplayed w toku...
echo Wszystkie nowe spektakularne akcje (Penta/Quadra/Clutch)
echo beda automatycznie montowane w tle z zerowym narzutem na FPS.
echo.
.\venv313\Scripts\python.exe -u lol_agent\autonomous\watcher.py
pause

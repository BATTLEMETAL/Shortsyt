@echo off
chcp 65001 >nul
title Shortsyt - Film 1 (14:00 PL)
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo ====================================================
echo  SHORTSYT - FILM 1 z 2 (PEAK: 14:00 PL)
echo ====================================================
echo Start: %date% %time%
echo.

cd /d "c:\Users\mz100\PycharmProjects\shortsyt"

if not exist "venv313\Scripts\python.exe" (
    echo BLAD KRYTYCZNY: Nie znaleziono venv313!
    exit /b 1
)

echo [1/3] Aktualizacja dyrektywy analitycznej...
"venv313\Scripts\python.exe" -u smart_video_analyzer.py

echo.
echo [2/3] Generacja i upload FILM 1 --quota 1...
"venv313\Scripts\python.exe" -u agent_dark_psychology.py --quota 1
set EXIT_CODE=%errorlevel%

echo.
echo [END] %date% %time% exit=%EXIT_CODE%
exit /b %EXIT_CODE%

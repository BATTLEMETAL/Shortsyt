@echo off
chcp 65001 >nul
title Shortsyt - Film 2 (19:00 PL)
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

echo ====================================================
echo  SHORTSYT - FILM 2 z 2 (PEAK: 19:00 PL)
echo ====================================================
echo Start: %date% %time%
echo.

cd /d "c:\Users\mz100\PycharmProjects\shortsyt"

if not exist "venv313\Scripts\python.exe" (
    echo BLAD KRYTYCZNY: Nie znaleziono venv313!
    exit /b 1
)

echo [1/2] Generacja i upload FILM 2 --quota 1...
"venv313\Scripts\python.exe" -u agent_dark_psychology.py --quota 1
set EXIT_CODE=%errorlevel%

echo.
echo [2/2] Post-analiza kanalow...
"venv313\Scripts\python.exe" -u smart_video_analyzer.py

echo.
echo [END] %date% %time% exit=%EXIT_CODE%
exit /b %EXIT_CODE%

@echo off
chcp 65001 >nul
title Shortsyt - Dark Psychology Daily Run

echo.
echo  ====================================================
echo   SHORTSYT - GENEROWANIE DAILY SHORTS
echo   Dark Psychology - 2 filmy dziennie (PUBLICZNE)
echo  ====================================================
echo.
echo  Uruchamiam pipeline o: %date% %time%
echo.

cd /d "c:\Users\mz100\PycharmProjects\shortsyt"
set PYTHONIOENCODING=utf-8

echo [1/2] Sprawdzam srodowisko...
if not exist "venv313\Scripts\python.exe" (
    echo BLAD: Nie znaleziono venv313! Sprawdz sciezke projektu.
    pause
    exit /b 1
)

echo [2/2] Uruchamiam agenta Dark Psychology...
echo.
"venv313\Scripts\python.exe" agent_dark_psychology.py 2>&1

echo.
if %ERRORLEVEL% EQU 0 (
    echo  ====================================================
    echo   SUKCES! 2 shortsy wygenerowane i wgrane jako PUBLICZNE.
    echo   Sprawdz YouTube Studio by je zatwierdzic.
    echo  ====================================================
) else (
    echo  ====================================================
    echo   BLAD! Cos poszlo nie tak. Sprawdz logi powyzej.
    echo  ====================================================
)

echo.
echo Nacisnij dowolny klawisz aby zamknac...
pause >nul

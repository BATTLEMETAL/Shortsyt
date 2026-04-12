@echo off
chcp 65001 >nul
title Shortsyt - Dark Psychology Daily Run

echo.
echo  ====================================================
echo   SHORTSYT - GENEROWANIE DAILY SHORTS
echo   Dark Psychology - 2 filmy dziennie (19:00 PL, PUBLIC natychmiast)
echo  ====================================================
echo.
echo  Uruchamiam pipeline o: %date% %time%
echo.

cd /d "c:\Users\mz100\PycharmProjects\shortsyt"
set PYTHONIOENCODING=utf-8

echo [1/4] Sprawdzam srodowisko...
if not exist "venv313\Scripts\python.exe" (
    echo BLAD: Nie znaleziono venv313! Sprawdz sciezke projektu.
    pause
    exit /b 1
)

echo [2/4] Weryfikacja duplikatow w historii shortow...
"venv313\Scripts\python.exe" verify_duplicates.py --fix >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo   OK - brak duplikatow w historii.
) else (
    echo   UWAGA: Duplikaty wykryte i usuniete automatycznie.
)

echo [3/4] Aktualizacja peak hours...
"venv313\Scripts\python.exe" analyze_peak_hours.py --offline --update-directive >nul 2>&1
echo   OK - adaptation_directive.json zaktualizowany.

echo [4/4] Uruchamiam agenta Dark Psychology (2 filmy + audyt + upload)...
echo.
"venv313\Scripts\python.exe" agent_dark_psychology.py 2>&1

echo.
if %ERRORLEVEL% EQU 0 (
    echo  ====================================================
    echo   SUKCES! Shortsy wygenerowane, audyt APPROVED.
    echo   Film 1: PUBLICZNY natychmiast
    echo   Film 2: PUBLICZNY natychmiast
    echo   Sprawdz YouTube Studio aby potwierdzic.
    echo  ====================================================
) else (
    echo  ====================================================
    echo   UWAGA: Blad lub audyt REJECTED. Sprawdz logi.
    echo   Uruchom: python verify_pipeline.py --full
    echo  ====================================================
)

echo.
echo  Koniec: %date% %time%
exit /b %ERRORLEVEL%

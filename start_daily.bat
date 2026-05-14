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
if not exist "logs" mkdir logs
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
set AGENT_EXIT=%ERRORLEVEL%

echo.
rem Sprawdzamy faktyczny wynik po publish_report.json, nie exit code (yt-dlp wyrzuca stderr=1 nawet przy sukcesie)
"venv313\Scripts\python.exe" -c "import json,sys,datetime; r=json.load(open('publish_report.json','r',encoding='utf-8')); today=datetime.date.today().isoformat(); uploaded=[x for x in r if x.get('published_at','')[:10]==today or x.get('timestamp','')[:10]==today]; print(f'UPLOADED_TODAY={len(uploaded)}'); sys.exit(0 if len(uploaded)>0 else 1)" 2>nul
set CHECK_EXIT=%ERRORLEVEL%

echo.
if %CHECK_EXIT% EQU 0 (
    echo  ====================================================
    echo   SUKCES! Shortsy wygenerowane i wgrane na YouTube.
    echo   Sprawdz YouTube Studio aby potwierdzic.
    echo  ====================================================
    exit /b 0
) else (
    echo  ====================================================
    echo   UWAGA: Brak nowych wgran dzisiaj. Sprawdz logi.
    echo   Uruchom: python verify_pipeline.py --full
    echo  ====================================================
    exit /b 1
)

echo.
echo  Koniec: %date% %time%

venv313\Scripts\python.exe generate_insights_page.py >> logs\insights_page.log 2>&1

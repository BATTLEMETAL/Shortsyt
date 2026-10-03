@echo off
setlocal
chcp 65001 >nul
title Shortsyt Mobile — Android Launcher
cd /d "%~dp0"

echo ========================================================
echo        SHORTSYT MOBILE — ANDROID APP LAUNCHER
echo ========================================================
echo.

:: 1. Sprawdź czy backend FastAPI działa
echo [1/3] Sprawdzanie serwera backendu FastAPI...
curl -s --connect-timeout 2 http://127.0.0.1:8765/health >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo       [OK] Backend FastAPI jest aktywny na porcie 8765.
) else (
    echo       Uruchamianie serwera FastAPI na 0.0.0.0:8765 w tle...
    start /min "Shortsyt API Backend" ".\venv313\Scripts\python.exe" -m uvicorn lol_agent.api.main:app --host 0.0.0.0 --port 8765
    timeout /t 3 /nobreak >nul
    echo       [OK] Backend wystartował.
)

:: 2. Wykryj lokalne IP dla telefonu
echo.
echo [2/3] Konfiguracja połączenia z telefonem:
for /f "tokens=4" %%a in ('route print ^| findstr "\<0.0.0.0\>"') do (
    set LOCAL_IP=%%a
    goto ip_found
)
:ip_found
echo       IP Twojego komputera w Wi-Fi: http://%LOCAL_IP%:8765
echo       Upewnij się, że telefon jest w tej samej sieci Wi-Fi!
echo.

:: 3. Sprawdź urządzenia ADB
echo [3/3] Wykrywanie urządzeń Android (ADB)...
set ADB_EXE=%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe
if exist "%ADB_EXE%" (
    "%ADB_EXE%" devices
) else (
    where adb >nul 2>&1 && adb devices
)

echo.
echo ========================================================
echo Wybierz jak chcesz przetestować aplikację:
echo [1] Uruchom serwer developerski Expo (kod QR / Expo Go)
echo [2] Zainstaluj gotowy APK bezpośrednio na podłączonym telefonie (ADB)
echo [3] Uruchom emulator Androida (Pixel Fold)
echo [4] Otwórz folder z gotowym plikiem instalacyjnym APK
echo [0] Wyjdź
echo ========================================================
set /p choice="Wybór [1-4, 0]: "

if "%choice%"=="1" goto start_expo
if "%choice%"=="2" goto install_apk
if "%choice%"=="3" goto start_emulator
if "%choice%"=="4" goto open_folder
goto end

:start_expo
echo.
echo Uruchamianie Expo Metro Bundler...
cd /d "%~dp0shortsyt-app"
npx expo start
goto end

:install_apk
echo.
set APK_PATH=%~dp0shortsyt-app\android\app\build\outputs\apk\debug\app-debug.apk
if not exist "%APK_PATH%" (
    echo [BŁĄD] Nie znaleziono pliku APK w: %APK_PATH%
    pause
    goto end
)
echo Instalowanie %APK_PATH% przez ADB...
if exist "%ADB_EXE%" (
    "%ADB_EXE%" install -r "%APK_PATH%"
) else (
    adb install -r "%APK_PATH%"
)
echo.
echo Instalacja zakończona! Możesz uruchomić aplikację na telefonie.
pause
goto end

:start_emulator
echo.
set EMU_EXE=%LOCALAPPDATA%\Android\Sdk\emulator\emulator.exe
if exist "%EMU_EXE%" (
    echo Uruchamianie emulatora Pixel_Fold_API_35...
    start "" "%EMU_EXE%" -avd Pixel_Fold_API_35
) else (
    echo [BŁĄD] Nie znaleziono emulatora w Android SDK.
)
pause
goto end

:open_folder
explorer /select,"%~dp0shortsyt-app\android\app\build\outputs\apk\debug\app-debug.apk"
goto end

:end
endlocal

@echo off
:: Skrypt wylaczajacy stare zaplanowane zadania Shortsyt w Harmonogramie Zadan Windows
:: Uruchom jako Administrator (Prawy przycisk myszy -> Uruchom jako administrator)
chcp 65001 >nul

echo ========================================================
echo   Wylaczanie starych zadan Shortsyt w Harmonogramie
echo ========================================================
echo.

schtasks /change /tn "ShortsytWeekly" /disable
if %errorlevel% equ 0 (
    echo [OK] ShortsytWeekly zostalo wylaczone.
) else (
    echo [UWAGA] Nie udalo sie wylaczyc ShortsytWeekly (wymaga uprawnien Administratora).
)

schtasks /change /tn "ShortsytMorning" /disable
if %errorlevel% equ 0 (
    echo [OK] ShortsytMorning zostalo wylaczone.
) else (
    echo [UWAGA] Nie udalo sie wylaczyc ShortsytMorning (wymaga uprawnien Administratora).
)

schtasks /change /tn "ShortsytEvening" /disable
if %errorlevel% equ 0 (
    echo [OK] ShortsytEvening zostalo wylaczone.
) else (
    echo [UWAGA] Nie udalo sie wylaczyc ShortsytEvening (wymaga uprawnien Administratora).
)

echo.
echo Gotowe. Nacisnij dowolny klawisz, aby zamknac...
pause >nul

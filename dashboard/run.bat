@echo off
echo ============================================================
echo  SHORTSYT DASHBOARD - Uruchamiam panel zarzadzania kontami
echo ============================================================
echo.
echo  Adres panelu: http://localhost:5000
echo  Zatrzymaj:    Ctrl+C
echo.
cd /d "%~dp0.."
.\venv313\Scripts\python.exe dashboard\app.py
pause

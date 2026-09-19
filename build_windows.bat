@echo off
REM Build a one-folder Windows exe with PyInstaller.
REM Run this ON Windows (PyInstaller produces Windows binaries only on Windows).
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
  ".venv\Scripts\python.exe" -m pip install -e .
)

echo Building with PyInstaller (one-folder)...
".venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name TradingRiskCalculator ^
  --paths src ^
  --collect-all customtkinter ^
  app.py

if errorlevel 1 (
  echo Build failed.
  pause
  exit /b 1
)

echo.
echo Done. Run: dist\TradingRiskCalculator\TradingRiskCalculator.exe
explorer dist\TradingRiskCalculator
pause

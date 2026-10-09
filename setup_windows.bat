@echo off
cd /d "%~dp0"
echo === Harvest Hand setup (Windows) ===
where py >nul 2>nul && (set PY=py -3) || (set PY=python)
%PY% --version >nul 2>nul || (echo Python is not installed. Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH". & pause & exit /b 1)
if not exist .venv %PY% -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt || (echo Install failed. & pause & exit /b 1)
if not exist .env copy .env.example .env >nul
echo.
echo Setup done. Double-click run_windows.bat to start the app.
pause

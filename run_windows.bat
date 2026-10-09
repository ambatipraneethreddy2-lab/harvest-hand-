@echo off
cd /d "%~dp0"
if not exist .venv (echo Run setup_windows.bat first. & pause & exit /b 1)
call .venv\Scripts\activate.bat
echo Harvest Hand is running at http://localhost:8000   (press Ctrl+C to stop)
start "" http://localhost:8000
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

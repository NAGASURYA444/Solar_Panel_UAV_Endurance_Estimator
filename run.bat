@echo off
cd /d "%~dp0"
echo Starting Solar UAV Endurance Estimator v2.0...
echo.

:: Check if venv exists
if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv .venv
)

call .venv\Scripts\activate.bat

:: Install dependencies if needed
echo Checking dependencies...
pip install -q -r app\requirements.txt

echo.
echo Server starting at http://localhost:8000
echo Press Ctrl+C to stop.
echo.

uvicorn app.main:app --reload --port 8000 --host 0.0.0.0

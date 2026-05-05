@echo off
cd /d "%~dp0"
echo ============================================
echo   Solar UAV Endurance Estimator v3.0
echo ============================================
echo.

:: ---- Step 1: Find a compatible Python (3.10 - 3.13) ----
set PYTHON_EXE=

for %%V in (3.13 3.12 3.11 3.10) do (
    if not defined PYTHON_EXE (
        py -%%V --version >nul 2>&1
        if not errorlevel 1 set PYTHON_EXE=py -%%V
    )
)

:: ---- Step 2: If not found, auto-install Python 3.13 via winget ----
if not defined PYTHON_EXE (
    echo No compatible Python found. Installing Python 3.13 automatically...
    echo This requires an internet connection and only happens once.
    echo.
    winget install Python.Python.3.13 --silent --accept-package-agreements --accept-source-agreements
    if errorlevel 1 (
        echo.
        echo ERROR: Could not install Python automatically.
        echo Please install Python 3.13 manually from https://www.python.org/downloads/
        echo Then double-click this file again.
        pause
        exit /b 1
    )
    echo.
    echo Python 3.13 installed successfully.

    :: Locate the newly installed python.exe
    if exist "%LOCALAPPDATA%\Programs\Python\Python313\python.exe" (
        set PYTHON_EXE="%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
    ) else if exist "C:\Program Files\Python313\python.exe" (
        set PYTHON_EXE="C:\Program Files\Python313\python.exe"
    ) else (
        echo.
        echo ERROR: Python installed but could not be located.
        echo Please close this window, reopen it, and double-click run.bat again.
        pause
        exit /b 1
    )
)

:: ---- Step 3: Create virtual environment if needed ----
if not exist ".venv\Scripts\activate.bat" (
    echo Setting up virtual environment...
    %PYTHON_EXE% -m venv .venv
    if errorlevel 1 (
        echo ERROR: Failed to create virtual environment.
        pause
        exit /b 1
    )
)

call .venv\Scripts\activate.bat

:: ---- Step 4: Install dependencies ----
echo Checking dependencies (first run may take a few minutes)...
pip install -q -r requirements.txt
if errorlevel 1 (
    echo ERROR: Failed to install dependencies.
    pause
    exit /b 1
)

:: ---- Step 5: Open browser and start server ----
echo.
echo ============================================
echo   Opening http://localhost:8000
echo   Press Ctrl+C to stop the server.
echo ============================================
echo.

start "" http://localhost:8000
uvicorn app.main:app --reload --port 8000 --host 0.0.0.0

pause

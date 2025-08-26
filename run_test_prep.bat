@echo off
REM Quick Test Preparation Launcher
REM This consolidates all discovered solutions and checks

echo.
echo ========================================
echo Algorithm Trading Platform Test Prep
echo ========================================
echo.

REM Navigate to script directory
cd /d "%~dp0"

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH
    echo Please ensure Python is installed and added to PATH
    pause
    exit /b 1
)

REM Try to activate virtual environment
if exist "venv\Scripts\activate.bat" (
    echo [INFO] Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo [WARNING] Virtual environment not found
)

REM Run the comprehensive preparation script
echo [INFO] Running comprehensive test preparation...
python test_preparation_script.py

echo.
echo ========================================
echo Test preparation completed!
echo ========================================
echo.

REM Keep window open if run by double-click
if "%1"=="" pause

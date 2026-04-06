@echo off
setlocal enabledelayedexpansion

REM ==========================================
REM       MOTO-RATER DASHBOARD LAUNCHER
REM ==========================================

REM --- Configuration ---
set "PACKAGES=pandas openpyxl plotly streamlit pingouin python-calamine pyarrow"
set "TOTAL_STEPS=8" 
set "VENV_DIR=venv"
set "MARKER_FILE=%VENV_DIR%\.installed"

REM --- 1. Check for Python ---
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [System] Python not found. Installing via Winget...
    winget install -e --id Python.Python.3.12
    set "PATH=%PATH%;%LOCALAPPDATA%\Programs\Python\Python312"
    
    python --version >nul 2>&1
    if %errorlevel% neq 0 (
        echo [Error] Python installation failed.
        pause
        exit /b
    )
)

REM --- 2. Check/Create Virtual Environment ---
if not exist "%VENV_DIR%" (
    cls
    echo ==================================================
    echo      First Time Setup: Creating Environment...
    echo ==================================================
    python -m venv "%VENV_DIR%"
)

REM --- 3. Activate Environment ---
call "%VENV_DIR%\Scripts\activate.bat"

REM --- 4. SMART CHECK: Are dependencies already installed? ---
if exist "%MARKER_FILE%" (
    REM === FAST LANE ===
    cls
    echo ==================================================
    echo      		MOTO-RATER DASHBOARD
    echo ==================================================
    echo.
    echo [System] Environment loaded.
    echo [System] Dependencies verified.
    echo.
    echo Launching App...
    goto :launch
)

REM === SLOW LANE (First Run Only) ===

REM --- 5. Installation Loop with Progress Bar ---
set current_step=0
set "bar="

REM -- Step 1: Upgrade Pip --
set /a current_step+=1
set "bar=[#.......]"
call :draw_progress "Upgrading Pip (Core Installer)"
python -m pip install --upgrade pip --quiet > install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

REM -- Step 2: Install Packages --
set /a current_step+=1
set "bar=[##......]"
call :draw_progress "Installing Pandas (Data Engine)"
pip install pandas --quiet >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

set /a current_step+=1
set "bar=[###.....]"
call :draw_progress "Installing Openpyxl (Excel Reader)"
pip install openpyxl --quiet >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

set /a current_step+=1
set "bar=[####....]"
call :draw_progress "Installing Plotly (Charting Engine)"
pip install plotly --quiet >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

set /a current_step+=1
set "bar=[#####...]"
call :draw_progress "Installing Pingouin"
pip install pingouin --quiet >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

set /a current_step+=1
set "bar=[######..]"
call :draw_progress "Installing Python Calamine - Efficient Excel reader"
pip install python-calamine --quiet >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

set /a current_step+=1
set "bar=[#######.]"
call :draw_progress "Installing Pyarrow - Parquet Files"
pip install pyarrow --quiet >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

set /a current_step+=1
set "bar=[########]"
call :draw_progress "Installing Streamlit (App Framework)"
pip install streamlit --quiet >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

REM --- 6. Create Marker File ---
REM This empty file tells the script next time that we are done.
type NUL > "%MARKER_FILE%"
if exist install_log.txt del install_log.txt

cls
echo ==================================================
echo [########] 100%% - Installation Complete
echo ==================================================
echo.
echo Launching MotoRater Dashboard...
timeout /t 2 >nul

:launch
streamlit run main.py
exit /b

REM --- Helper Function: Draw Progress ---
:draw_progress
cls
echo ==================================================
echo      	MOTO-RATER DASHBOARD SETUP
echo ==================================================
echo.
echo %bar% Step %current_step%/%TOTAL_STEPS%
echo.
echo Current Task: %~1
echo.
echo (First time setup: Please wait...)
echo ==================================================
exit /b

REM --- Error Handler ---
:error
echo.
echo [ERROR] An error occurred during installation.
echo Details:
type install_log.txt
pause
exit /b
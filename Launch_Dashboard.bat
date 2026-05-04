@echo off
setlocal enabledelayedexpansion

REM --- 0. Lock working directory to the script's exact location ---
pushd "%~dp0"

REM ==========================================
REM    MOTO-RATER DASHBOARD LAUNCHER
REM ==========================================

REM --- Configuration ---
set "GITHUB_ZIP_URL=https://github.com/bernas-estevam97/MotoRater-Dashboard/archive/refs/heads/dev.zip"
set "GITHUB_EXTRACT_FOLDER=MotoRater-Dashboard-dev"

set "PYTHON_URL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
set "PIP_URL=https://bootstrap.pypa.io/get-pip.py"
set "TOTAL_STEPS=10" 
set "ENV_DIR=python_env"
set "MARKER_FILE=%ENV_DIR%\.installed"
set "PYTHON_EXE=%ENV_DIR%\python.exe"

REM --- Pre-Flight Checks ---
echo test > ".testwrite" 2>nul
if not exist ".testwrite" (
    echo [ERROR] No write permissions in this directory.
    echo Please move the Moto-Rater folder to your Desktop or Documents folder.
    pause
    exit /b
)
del ".testwrite"

where curl >nul 2>nul
if %errorlevel% neq 0 ( echo [ERROR] 'curl' is required but missing. Windows 10+ is needed. & pause & exit /b )
where tar >nul 2>nul
if %errorlevel% neq 0 ( echo [ERROR] 'tar' is required but missing. Windows 10+ is needed. & pause & exit /b )

REM --- 1. SMART CHECK: Is Python already installed? ---
if exist "%MARKER_FILE%" (
    REM === FAST LANE ===
    cls
    echo ==================================================
    echo             MOTO-RATER DASHBOARD
    echo ==================================================
    echo.
    echo [System] Portable environment loaded.
    echo [System] Dependencies verified.
    echo.
    goto :check_app_files
)

REM === SLOW LANE (First Run Only) ===
set current_step=0
set "bar="

if not exist "%ENV_DIR%" mkdir "%ENV_DIR%"

REM -- Step 1: Download Portable Python --
set /a current_step+=1
set "bar=[#.........]"
call :draw_progress "Downloading Portable Python..."
curl -L -o python.zip %PYTHON_URL% --silent
if %errorlevel% neq 0 goto :error

REM -- Step 2: Extract Python --
set /a current_step+=1
set "bar=[##........]"
call :draw_progress "Extracting Python Engine..."
tar -xf python.zip -C "%ENV_DIR%"
del python.zip
if %errorlevel% neq 0 goto :error

REM -- Step 3: Enable Pip Configuration --
set /a current_step+=1
set "bar=[###.......]"
call :draw_progress "Configuring Environment..."
for %%F in ("%ENV_DIR%\*._pth") do (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content '%%F') -replace '#import site', 'import site' | Set-Content '%%F'"
)

REM -- Step 4: Install Pip --
set /a current_step+=1
set "bar=[####......]"
call :draw_progress "Installing Pip (Core Installer)..."
curl -L -o "%ENV_DIR%\get-pip.py" %PIP_URL% --silent
"%PYTHON_EXE%" "%ENV_DIR%\get-pip.py" --no-warn-script-location > install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

REM -- Step 5: Install Pandas --
set /a current_step+=1
set "bar=[#####.....]"
call :draw_progress "Installing Pandas (Data Engine)..."
"%PYTHON_EXE%" -m pip install pandas --no-warn-script-location --quiet >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

REM -- Step 6: Install Openpyxl and Plotly --
set /a current_step+=1
set "bar=[######....]"
call :draw_progress "Installing Plotly and Openpyxl..."
"%PYTHON_EXE%" -m pip install openpyxl plotly --no-warn-script-location --quiet >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

REM -- Step 7: Install Pingouin --
set /a current_step+=1
set "bar=[#######...]"
call :draw_progress "Installing Pingouin..."
"%PYTHON_EXE%" -m pip install pingouin --no-warn-script-location --quiet >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

REM -- Step 8: Install Calamine --
set /a current_step+=1
set "bar=[########..]"
call :draw_progress "Installing Python Calamine..."
"%PYTHON_EXE%" -m pip install python-calamine --no-warn-script-location --quiet >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

REM -- Step 9: Install Pyarrow --
set /a current_step+=1
set "bar=[#########.]"
call :draw_progress "Installing Pyarrow..."
"%PYTHON_EXE%" -m pip install pyarrow --no-warn-script-location --quiet >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

REM -- Step 10: Install Streamlit --
set /a current_step+=1
set "bar=[##########]"
call :draw_progress "Installing Streamlit (App Framework)..."
"%PYTHON_EXE%" -m pip install streamlit --no-warn-script-location --quiet >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

REM --- Finalizing Setup ---
type NUL > "%MARKER_FILE%"
if exist install_log.txt del install_log.txt

cls
echo ==================================================
echo [##########] 100%% - Installation Complete
echo ==================================================
echo.

:check_app_files
REM --- SELF-HEALING: Check if app files exist, download if missing ---
if not exist "main.py" (
    echo [System] App source code missing. Fetching from GitHub...
    curl -L -o app_code.zip "%GITHUB_ZIP_URL%" --silent
    if exist app_code.zip (
        tar -xf app_code.zip
        if exist "%GITHUB_EXTRACT_FOLDER%" (
            REM Prevent the script from overwriting itself by deleting batch files from the downloaded code first
            del /q "%GITHUB_EXTRACT_FOLDER%\*.bat" 2>nul
            xcopy /s /y /q "%GITHUB_EXTRACT_FOLDER%\*" . >nul
            rmdir /s /q "%GITHUB_EXTRACT_FOLDER%"
        )
        del app_code.zip
        echo [System] App code successfully downloaded.
    ) else (
        echo [ERROR] Failed to download app files. Please check your internet connection.
        pause
        exit /b
    )
)

echo Launching MotoRater Dashboard...
timeout /t 2 >nul

:launch
REM Call Streamlit explicitly through the portable Python executable
"%PYTHON_EXE%" -m streamlit run main.py
exit /b

REM --- Helper Function: Draw Progress ---
:draw_progress
cls
echo ==================================================
echo         MOTO-RATER DASHBOARD SETUP
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
@echo off
setlocal enabledelayedexpansion

REM --- 0. Lock working directory to the script's exact location ---
pushd "%~dp0"

REM ==========================================
REM    MOTO-RATER DASHBOARD LAUNCHER & UPDATER
REM ==========================================

REM --- Configuration ---
set "GITHUB_ZIP_URL=https://github.com/bernas-estevam97/MotoRater-Dashboard/archive/refs/heads/dev.zip"
set "GITHUB_EXTRACT_FOLDER=MotoRater-Dashboard-dev"

set "PYTHON_URL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
set "PIP_URL=https://bootstrap.pypa.io/get-pip.py"
set "ENV_DIR=python_env"
set "MARKER_FILE=%ENV_DIR%\.installed"
set "PYTHON_EXE=%ENV_DIR%\python.exe"

REM Check for write permissions
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

REM --- GitHub Update Check ---
cls
echo ==================================================
echo             MOTO-RATER DASHBOARD
echo ==================================================
echo.
choice /c YN /t 4 /d N /m "Check for app updates from GitHub? (Requires Internet)"
if errorlevel 2 goto :skip_update
if errorlevel 1 (
    echo.
    echo [System] Fetching latest update from GitHub...
    curl -L -o app_update.zip "%GITHUB_ZIP_URL%" --silent
    if exist app_update.zip (
        (
            tar -xf app_update.zip
            if exist "%GITHUB_EXTRACT_FOLDER%" (
                xcopy /s /y /q "%GITHUB_EXTRACT_FOLDER%\*" . >nul
                rmdir /s /q "%GITHUB_EXTRACT_FOLDER%"
            )
            del app_update.zip
        )
        echo [System] Update complete!
        timeout /t 2 >nul
    ) else (
        echo [ERROR] Failed to download update. Skipping...
        timeout /t 2 >nul
    )
)
:skip_update

REM --- SMART CHECK: Local venv vs Portable Python ---
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
    set "ENV_DIR=venv"
    echo.
    echo [System] Using virtual environment (venv).
    goto :launch
)

if exist "%MARKER_FILE%" (
    cls
    echo ==================================================
    echo             MOTO-RATER DASHBOARD
    echo ==================================================
    echo.
    echo [System] Portable environment loaded.
    echo [System] Dependencies verified.
    echo.
    echo Launching App...
    goto :launch
)

REM === SLOW LANE (First Run Only - Portable Python) ===
set TOTAL_STEPS=6
set current_step=0
set "bar="

if not exist "%ENV_DIR%" mkdir "%ENV_DIR%"

set /a current_step+=1
set "bar=[#.....]"
call :draw_progress "Downloading Portable Python..."
curl -L -o python.zip %PYTHON_URL% --silent
if %errorlevel% neq 0 goto :error

set /a current_step+=1
set "bar=[##....]"
call :draw_progress "Extracting Python Engine..."
tar -xf python.zip -C "%ENV_DIR%"
del python.zip
if %errorlevel% neq 0 goto :error

set /a current_step+=1
set "bar=[###...]"
call :draw_progress "Configuring Environment..."
for %%F in ("%ENV_DIR%\*._pth") do (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content '%%F') -replace '#import site', 'import site' | Set-Content '%%F'"
)

set /a current_step+=1
set "bar=[####..]"
call :draw_progress "Installing Pip (Core Installer)..."
curl -L -o "%ENV_DIR%\get-pip.py" %PIP_URL% --silent
"%PYTHON_EXE%" "%ENV_DIR%\get-pip.py" --no-warn-script-location > install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

set /a current_step+=1
set "bar=[#####.]"
call :draw_progress "Installing App Dependencies..."
if exist "requirements.txt" (
    "%PYTHON_EXE%" -m pip install -r requirements.txt --no-warn-script-location --quiet >> install_log.txt 2>&1
) else (
    "%PYTHON_EXE%" -m pip install pandas openpyxl plotly pingouin python-calamine pyarrow streamlit polars statsmodels joblib streamlit-javascript tables psutil scikit-learn matplotlib --no-warn-script-location --quiet >> install_log.txt 2>&1
)
if %errorlevel% neq 0 goto :error

set /a current_step+=1
set "bar=[######]"
call :draw_progress "Verifying Installation..."
"%PYTHON_EXE%" -c "import streamlit, pandas, polars, statsmodels" >> install_log.txt 2>&1
if %errorlevel% neq 0 goto :error

type NUL > "%MARKER_FILE%"
if exist install_log.txt del install_log.txt

cls
echo ==================================================
echo [######] 100%% - Installation Complete
echo ==================================================
echo.

:launch
"%PYTHON_EXE%" -m streamlit run main.py
exit /b

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

:error
echo.
echo [ERROR] An error occurred during installation.
echo Details:
type install_log.txt
pause
exit /b
@echo off
setlocal enabledelayedexpansion

REM --- Lock working directory to the script's location ---
pushd "%~dp0"

REM ==========================================
REM    MOTO-RATER DASHBOARD LAUNCHER
REM    1. Uses venv\ if present, otherwise a portable Python in python_env\ (installed on first run)
REM    2. Re-installs dependencies when an update changed requirements.txt
REM    3. Starts the dashboard
REM ==========================================

set "PYTHON_URL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-embed-amd64.zip"
set "PIP_URL=https://bootstrap.pypa.io/get-pip.py"
set "ENV_DIR=python_env"
set "MARKER_FILE=%ENV_DIR%\.installed"
set "PYTHON_EXE=%ENV_DIR%\python.exe"
set "LOG=install_log.txt"
set "GITHUB_ZIP_URL=https://github.com/bernas-estevam97/MotoRater-Dashboard/archive/refs/heads/prod_pro.zip"

REM --- Pre-flight checks ---
echo test > ".testwrite" 2>nul
if not exist ".testwrite" (
    echo [ERROR] No write permission in this folder.
    echo Move the MotoRater folder to your Desktop or Documents and try again.
    goto :fail
)
del ".testwrite"

REM --- Self-healing: fetch the app if only this launcher was downloaded ---
if not exist "main.py" (
    echo [System] App files missing - downloading from GitHub...
    if exist "Updater.bat" (
        call "Updater.bat" /silent
    ) else (
        curl -fsSL -o app_code.zip "%GITHUB_ZIP_URL%" && tar -xf app_code.zip && del app_code.zip
        for /d %%D in ("MotoRater-Dashboard-*") do (
            del /q "%%D\Launch_Dashboard.bat" 2>nul
            xcopy /s /e /y /q "%%D\*" . >nul
            rmdir /s /q "%%D"
        )
    )
    REM Restart from the freshly downloaded copy of this launcher (no CALL = hand over control).
    if exist "main.py" "%~f0"
)
if not exist "main.py" (
    echo [ERROR] Could not download the app. Check your internet connection.
    goto :fail
)

REM --- 1. Existing virtual environment? ---
if exist "venv\Scripts\python.exe" (
    set "PYTHON_EXE=venv\Scripts\python.exe"
    call :banner "Using virtual environment (venv)."
    goto :deps
)

REM --- 2. Portable Python already installed? ---
if exist "%MARKER_FILE%" (
    call :banner "Using portable Python environment."
    goto :deps
)

REM === FIRST RUN: install portable Python ===
where curl >nul 2>nul || ( echo [ERROR] 'curl' is missing. Windows 10 or newer is required. & goto :fail )
where tar  >nul 2>nul || ( echo [ERROR] 'tar' is missing. Windows 10 or newer is required. & goto :fail )
if not exist "%ENV_DIR%" mkdir "%ENV_DIR%"
type NUL > "%LOG%"

call :step 1 "Downloading portable Python..."
curl -fsSL -o python.zip "%PYTHON_URL%" >> "%LOG%" 2>&1 || goto :error

call :step 2 "Extracting Python..."
tar -xf python.zip -C "%ENV_DIR%" >> "%LOG%" 2>&1 || goto :error
del python.zip

call :step 3 "Configuring environment..."
for %%F in ("%ENV_DIR%\*._pth") do (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "(Get-Content '%%F') -replace '#import site', 'import site' | Set-Content '%%F'"
)

call :step 4 "Installing pip..."
curl -fsSL -o "%ENV_DIR%\get-pip.py" "%PIP_URL%" >> "%LOG%" 2>&1 || goto :error
"%PYTHON_EXE%" "%ENV_DIR%\get-pip.py" --no-warn-script-location >> "%LOG%" 2>&1 || goto :error

call :step 5 "Installing app dependencies (this can take several minutes)..."
call :install_deps || goto :error

call :step 6 "Verifying installation..."
"%PYTHON_EXE%" -c "import streamlit, pandas, statsmodels, pingouin" >> "%LOG%" 2>&1 || goto :error

type NUL > "%MARKER_FILE%"
del "%LOG%" 2>nul
call :banner "Installation complete."

:deps
REM --- Refresh dependencies after an update changed requirements.txt ---
if exist ".deps_outdated" (
    echo [System] requirements.txt changed - updating dependencies...
    type NUL > "%LOG%"
    call :install_deps || goto :error
    del ".deps_outdated"
    del "%LOG%" 2>nul
)

echo [System] Launching MotoRater Dashboard - your browser will open shortly.
echo [System] Close this window to stop the dashboard.
"%PYTHON_EXE%" -m streamlit run main.py --browser.gatherUsageStats false
popd
exit /b 0

REM ================= Subroutines =================
:install_deps
"%PYTHON_EXE%" -m pip install -r requirements.txt --no-warn-script-location --quiet >> "%LOG%" 2>&1
exit /b %errorlevel%

:banner
cls
echo ==================================================
echo             MOTO-RATER DASHBOARD
echo ==================================================
echo.
echo [System] %~1
echo.
exit /b 0

:step
cls
echo ==================================================
echo         MOTO-RATER DASHBOARD - FIRST-TIME SETUP
echo ==================================================
echo.
echo Step %~1/6: %~2
echo.
echo Please wait. Details are written to %LOG%.
echo ==================================================
exit /b 0

:error
echo.
echo [ERROR] Setup failed. Last lines of %LOG%:
echo --------------------------------------------------
powershell -NoProfile -Command "Get-Content '%LOG%' -Tail 25"
echo --------------------------------------------------
echo Fix the problem above (often: no internet connection) and run this file again.

:fail
pause
popd
exit /b 1

@echo off
setlocal enabledelayedexpansion

REM --- 0. Lock working directory to the script's exact location ---
pushd "%~dp0"

REM ==========================================
REM    MOTO-RATER DASHBOARD UPDATER
REM ==========================================

REM --- Configuration ---
set "GITHUB_ZIP_URL=https://github.com/bernas-estevam97/MotoRater-Dashboard/archive/refs/heads/dev.zip"
set "GITHUB_EXTRACT_FOLDER=MotoRater-Dashboard-dev"

cls
echo ==================================================
echo       MOTO-RATER DASHBOARD - UPDATER
echo ==================================================
echo.
echo This will fetch the latest development version from GitHub.
echo.
echo IMPORTANT: Please ensure the dashboard is closed before proceeding.
echo.
pause

echo.
echo [System] Fetching latest update from GitHub...
curl -L -o app_update.zip "%GITHUB_ZIP_URL%" --silent

if exist app_update.zip (
    REM Extract and overwrite
    tar -xf app_update.zip
    if exist "%GITHUB_EXTRACT_FOLDER%" (
        xcopy /s /y /q "%GITHUB_EXTRACT_FOLDER%\*" . >nul
        rmdir /s /q "%GITHUB_EXTRACT_FOLDER%"
    )
    del app_update.zip
    
    echo.
    echo [System] Update complete! You can now launch the dashboard.
) else (
    echo.
    echo [ERROR] Failed to download update. Please check your internet connection.
)

echo.
pause
exit /b
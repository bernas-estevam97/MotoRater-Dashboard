@echo off
setlocal enabledelayedexpansion

REM --- Lock working directory to the script's location ---
pushd "%~dp0"

REM ==========================================
REM    MOTO-RATER DASHBOARD UPDATER
REM    Usage: Updater.bat           (interactive)
REM           Updater.bat /silent   (no prompts, used by Update_Launch_App.bat)
REM ==========================================

REM --- Configuration: GitHub branch this installation follows ---
set "BRANCH=prod_pro"
set "REPO=bernas-estevam97/MotoRater-Dashboard"
set "GITHUB_ZIP_URL=https://github.com/%REPO%/archive/refs/heads/%BRANCH%.zip"
set "GITHUB_EXTRACT_FOLDER=MotoRater-Dashboard-%BRANCH%"

set "SILENT=0"
if /i "%~1"=="/silent" set "SILENT=1"

if "%SILENT%"=="0" (
    cls
    echo ==================================================
    echo       MOTO-RATER DASHBOARD - UPDATER
    echo ==================================================
    echo.
    echo Fetches the latest version of branch "%BRANCH%" from GitHub.
    echo IMPORTANT: close the dashboard before continuing.
    echo.
    pause
)

where curl >nul 2>nul || ( echo [ERROR] 'curl' is missing. Windows 10 or newer is required. & goto :done )
where tar  >nul 2>nul || ( echo [ERROR] 'tar' is missing. Windows 10 or newer is required. & goto :done )

echo.
echo [Update] Downloading %BRANCH% from GitHub...
if exist app_update.zip del app_update.zip
REM -f makes curl fail on HTTP errors (e.g. 404) instead of saving an error page as the zip.
curl -fsSL -o app_update.zip "%GITHUB_ZIP_URL%"
if errorlevel 1 (
    echo [ERROR] Download failed. Check your internet connection and that branch "%BRANCH%" exists on GitHub.
    if exist app_update.zip del app_update.zip
    goto :done
)

if exist "%GITHUB_EXTRACT_FOLDER%" rmdir /s /q "%GITHUB_EXTRACT_FOLDER%"
tar -xf app_update.zip
del app_update.zip
if not exist "%GITHUB_EXTRACT_FOLDER%\main.py" (
    echo [ERROR] Downloaded archive is incomplete. Nothing was changed.
    if exist "%GITHUB_EXTRACT_FOLDER%" rmdir /s /q "%GITHUB_EXTRACT_FOLDER%"
    goto :done
)

REM Flag a dependency refresh when requirements.txt changed (handled by Launch_Dashboard.bat).
if exist requirements.txt (
    fc /b requirements.txt "%GITHUB_EXTRACT_FOLDER%\requirements.txt" >nul 2>nul || type NUL > .deps_outdated
)

REM Copy everything and exit inside ONE parenthesized block: cmd parses the whole block
REM before running it, so overwriting this .bat file while it runs is safe.
(
    xcopy /s /e /y /q "%GITHUB_EXTRACT_FOLDER%\*" . >nul
    rmdir /s /q "%GITHUB_EXTRACT_FOLDER%"
    echo [Update] Update complete.
    if "%SILENT%"=="0" pause
    popd
    exit /b 0
)

:done
if "%SILENT%"=="0" pause
popd
exit /b 1

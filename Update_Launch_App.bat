@echo off
REM ==========================================
REM    MOTO-RATER DASHBOARD - UPDATE AND LAUNCH (daily use)
REM    Offers a GitHub update (Updater.bat), then starts Launch_Dashboard.bat.
REM ==========================================
pushd "%~dp0"
cls
echo ==================================================
echo             MOTO-RATER DASHBOARD
echo ==================================================
echo.
choice /c YN /t 5 /d N /m "Check GitHub for app updates? (auto-skips in 5 s)"
set "DO_UPDATE=%errorlevel%"

REM The block below is parsed by cmd in one go, so Updater.bat may safely overwrite
REM this file while it runs (re-reading a modified .bat mid-run would break it).
(
    if "%DO_UPDATE%"=="1" call "Updater.bat" /silent
    call "Launch_Dashboard.bat"
    popd
    exit /b
)

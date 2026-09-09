<#
.SYNOPSIS
    MotoRater Dashboard Launcher
.DESCRIPTION
    Checks Python, sets up a virtual environment, installs dependencies 
    with a visual progress bar, and launches the Streamlit app.
#>

$ErrorActionPreference = "Stop"

# --- Configuration ---
$VenvDir = Join-Path $PSScriptRoot "venv"
$MarkerFile = Join-Path $VenvDir ".installed"
$LogFile = Join-Path $PSScriptRoot "install_log.txt"
$AppScript = Join-Path $PSScriptRoot "app.py"

# Define packages to install
$Packages = @("pandas", "openpyxl", "plotly", "streamlit")

# --- Helper: Check Python ---
function Check-Python {
    try {
        $null = Get-Command "python" -ErrorAction Stop
    }
    catch {
        Write-Host "[System] Python not found. Attempting install..." -ForegroundColor Yellow
        winget install -e --id Python.Python.3.11
        # Refresh env logic would go here, but usually requires a restart.
        Write-Error "Python was missing. Installation attempted. Please restart this script."
    }
}

# --- Main Logic ---

Clear-Host
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "     MOTO-RATER DASHBOARD LAUNCHER"
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

Check-Python

# 1. Create Venv (if missing)
if (-not (Test-Path $VenvDir)) {
    Write-Host "[Init] Creating virtual environment..." -ForegroundColor Gray
    python -m venv $VenvDir
}

# Define paths to venv executables
$PipExe = Join-Path $VenvDir "Scripts\pip.exe"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$StreamlitExe = Join-Path $VenvDir "Scripts\streamlit.exe"

# 2. Smart Check (Fast Lane)
if (Test-Path $MarkerFile) {
    Write-Host "[Check] Dependencies already installed." -ForegroundColor Green
    Write-Host "[Launch] Starting Dashboard..." -ForegroundColor Green
    Start-Sleep -Seconds 1
    
    # Run App
    & $StreamlitExe run $AppScript
    exit
}

# 3. Installation Loop (Slow Lane)
Write-Host "[Setup] Installing dependencies..." -ForegroundColor Yellow

try {
    # Initialize Log
    "Installation Started: $(Get-Date)" | Out-File $LogFile -Encoding UTF8

    # Upgrade Pip first
    Write-Progress -Activity "MotoRater Setup" -Status "Upgrading Pip..." -PercentComplete 0
    & $PythonExe -m pip install --upgrade pip --quiet 2>> $LogFile

    # Loop through packages
    for ($i = 0; $i -lt $Packages.Count; $i++) {
        $pkg = $Packages[$i]
        
        # Calculate Percentage
        $percent = (($i + 1) / $Packages.Count) * 100
        
        # Update the Blue Progress Bar at the top of the console
        Write-Progress -Activity "MotoRater Setup" -Status "Installing $pkg..." -PercentComplete $percent
        
        # Run Install Command
        & $PipExe install $pkg --quiet 2>> $LogFile
    }

    # Complete Progress Bar
    Write-Progress -Activity "MotoRater Setup" -Status "Finalizing..." -Completed

    # Create Marker
    New-Item -Path $MarkerFile -ItemType File -Force | Out-Null
    
    Write-Host "[Success] Installation Complete!" -ForegroundColor Green
    Start-Sleep -Seconds 1

    # Run App
    & $StreamlitExe run $AppScript

}
catch {
    Write-Progress -Activity "Setup" -Completed
    Write-Host ""
    Write-Host "[ERROR] Installation failed." -ForegroundColor Red
    Write-Host "Check $LogFile for details." -ForegroundColor Gray
    Read-Host "Press Enter to exit"
}
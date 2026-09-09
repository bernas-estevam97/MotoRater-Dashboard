#!/usr/bin/env bash

# --- 0. Lock working directory to the script's exact location ---
cd "$(dirname "$0")" || exit

# ==========================================
#    MOTO-RATER DASHBOARD LAUNCHER (MAC)
# ==========================================

# --- Configuration ---
GITHUB_ZIP_URL="https://github.com/bernas-estevam97/MotoRater-Dashboard/archive/refs/heads/dev.zip"
GITHUB_EXTRACT_FOLDER="MotoRater-Dashboard-dev"

ENV_DIR="python_env"
MARKER_FILE="$ENV_DIR/.installed"
PYTHON_EXE="$ENV_DIR/bin/python3"
PIP_EXE="$ENV_DIR/bin/pip"
STREAMLIT_EXE="$ENV_DIR/bin/streamlit"

# --- Helper Function: Draw Progress ---
draw_progress() {
    clear
    echo "=================================================="
    echo "        MOTO-RATER DASHBOARD SETUP"
    echo "=================================================="
    echo ""
    echo "$1 Step $2/4"
    echo ""
    echo "Current Task: $3"
    echo ""
    echo "(First time setup: Please wait...)"
    echo "=================================================="
}

# --- Helper Function: Error Handler ---
error_exit() {
    echo ""
    echo "[ERROR] An error occurred during installation."
    echo "Details:"
    cat install_log.txt
    read -p "Press Enter to exit..."
    exit 1
}

# --- Pre-Flight Checks ---
touch ".testwrite" 2>/dev/null
if [ ! -f ".testwrite" ]; then
    echo "[ERROR] No write permissions in this directory."
    echo "Please move the Moto-Rater folder to your Desktop or Documents folder."
    read -p "Press Enter to exit..."
    exit 1
fi
rm -f ".testwrite"

if ! command -v curl &> /dev/null; then echo "[ERROR] 'curl' is required but missing." && read -p "Press Enter to exit..." && exit 1; fi
if ! command -v tar &> /dev/null; then echo "[ERROR] 'tar' is required but missing." && read -p "Press Enter to exit..." && exit 1; fi

# Check if an existing venv is available
if [ -f "venv/bin/streamlit" ]; then
    clear
    echo "=================================================="
    echo "            MOTO-RATER DASHBOARD"
    echo "=================================================="
    echo ""
    echo "[System] Local virtual environment (venv) detected."
    STREAMLIT_EXE="venv/bin/streamlit"
elif [ -f "$MARKER_FILE" ]; then
    # === FAST LANE ===
    clear
    echo "=================================================="
    echo "            MOTO-RATER DASHBOARD"
    echo "=================================================="
    echo ""
    echo "[System] Portable environment loaded."
    echo "[System] Dependencies verified."
    echo ""
else
    # Check if Python 3 is installed
    if ! command -v python3 &> /dev/null; then
        echo "[ERROR] Python 3 is not installed or not in your PATH."
        echo "Please open Terminal and run: xcode-select --install"
        read -p "Press Enter to exit..."
        exit 1
    fi

    # === SLOW LANE (First Run Only) ===
    draw_progress "[#...]" "1" "Creating Virtual Environment..."
    python3 -m venv "$ENV_DIR" > install_log.txt 2>&1 || error_exit

    draw_progress "[##..]" "2" "Upgrading Pip..."
    "$PIP_EXE" install --upgrade pip --quiet >> install_log.txt 2>&1 || error_exit

    draw_progress "[###.]" "3" "Installing Dependencies from requirements.txt..."
    if [ -f "requirements.txt" ]; then
        "$PIP_EXE" install -r requirements.txt --quiet >> install_log.txt 2>&1 || error_exit
    else
        "$PIP_EXE" install streamlit pandas openpyxl plotly pingouin python-calamine pyarrow polars statsmodels joblib streamlit-javascript tables psutil scikit-learn matplotlib --quiet >> install_log.txt 2>&1 || error_exit
    fi

    draw_progress "[####]" "4" "Verifying Installation..."
    "$PYTHON_EXE" -c "import streamlit, pandas, polars, statsmodels" >> install_log.txt 2>&1 || error_exit

    # --- Finalizing Setup ---
    touch "$MARKER_FILE"
    rm -f install_log.txt

    clear
    echo "=================================================="
    echo "[####] 100% - Installation Complete"
    echo "=================================================="
    echo ""
fi

# --- SELF-HEALING: Check if app files exist, download if missing ---
if [ ! -f "main.py" ]; then
    echo "[System] App source code missing. Fetching from GitHub..."
    curl -L -o app_code.zip "$GITHUB_ZIP_URL" --silent
    if [ -f "app_code.zip" ]; then
        tar -xf app_code.zip
        if [ -d "$GITHUB_EXTRACT_FOLDER" ]; then
            rm -f "$GITHUB_EXTRACT_FOLDER/Launch_Dashboard.command" 2>/dev/null
            cp -R "$GITHUB_EXTRACT_FOLDER/"* . >/dev/null 2>&1
            rm -rf "$GITHUB_EXTRACT_FOLDER"
            chmod +x *.command 2>/dev/null
        fi
        rm -f app_code.zip
        echo "[System] App code successfully downloaded."
    else
        echo "[ERROR] Failed to download app files. Please check internet connection."
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

echo "Launching MotoRater Dashboard..."
sleep 2

# --- Launch App ---
"$STREAMLIT_EXE" run main.py
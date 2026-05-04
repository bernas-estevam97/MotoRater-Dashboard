#!/usr/bin/env bash

# --- 0. Lock working directory to the script's exact location ---
cd "$(dirname "$0")" || exit

# ==========================================
#    MOTO-RATER DASHBOARD LAUNCHER (MAC)
# ==========================================

# --- Configuration ---
GITHUB_ZIP_URL="https://github.com/bernas-estevam97/MotoRater-Dashboard/archive/refs/heads/dev.zip"
GITHUB_EXTRACT_FOLDER="MotoRater-Dashboard-dev"

TOTAL_STEPS=8
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
    echo "$1 Step $2/$TOTAL_STEPS"
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

# Check if Python 3 is installed (macOS usually includes this)
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed or not in your PATH."
    echo "macOS will usually prompt you to install it if you open your Terminal"
    echo "and run the command: xcode-select --install"
    read -p "Press Enter to exit..."
    exit 1
fi

# --- 1. SMART CHECK: Is Python environment installed? ---
if [ ! -f "$MARKER_FILE" ]; then
    # === SLOW LANE (First Run Only) ===
    
    CURRENT_STEP=1
    BAR="[#.......]"
    draw_progress "$BAR" "$CURRENT_STEP" "Creating Virtual Environment..."
    python3 -m venv "$ENV_DIR" > install_log.txt 2>&1 || error_exit

    CURRENT_STEP=2
    BAR="[##......]"
    draw_progress "$BAR" "$CURRENT_STEP" "Upgrading Pip..."
    "$PIP_EXE" install --upgrade pip --quiet >> install_log.txt 2>&1 || error_exit

    CURRENT_STEP=3
    BAR="[###.....]"
    draw_progress "$BAR" "$CURRENT_STEP" "Installing Pandas (Data Engine)..."
    "$PIP_EXE" install pandas --quiet >> install_log.txt 2>&1 || error_exit

    CURRENT_STEP=4
    BAR="[####....]"
    draw_progress "$BAR" "$CURRENT_STEP" "Installing Plotly and Openpyxl..."
    "$PIP_EXE" install openpyxl plotly --quiet >> install_log.txt 2>&1 || error_exit

    CURRENT_STEP=5
    BAR="[#####...]"
    draw_progress "$BAR" "$CURRENT_STEP" "Installing Pingouin..."
    "$PIP_EXE" install pingouin --quiet >> install_log.txt 2>&1 || error_exit

    CURRENT_STEP=6
    BAR="[######..]"
    draw_progress "$BAR" "$CURRENT_STEP" "Installing Python Calamine..."
    "$PIP_EXE" install python-calamine --quiet >> install_log.txt 2>&1 || error_exit

    CURRENT_STEP=7
    BAR="[#######.]"
    draw_progress "$BAR" "$CURRENT_STEP" "Installing Pyarrow..."
    "$PIP_EXE" install pyarrow --quiet >> install_log.txt 2>&1 || error_exit

    CURRENT_STEP=8
    BAR="[########]"
    draw_progress "$BAR" "$CURRENT_STEP" "Installing Streamlit (App Framework)..."
    "$PIP_EXE" install streamlit --quiet >> install_log.txt 2>&1 || error_exit

    # --- Finalizing Setup ---
    touch "$MARKER_FILE"
    rm -f install_log.txt

    clear
    echo "=================================================="
    echo "[########] 100% - Installation Complete"
    echo "=================================================="
    echo ""
else
    # === FAST LANE ===
    clear
    echo "=================================================="
    echo "            MOTO-RATER DASHBOARD"
    echo "=================================================="
    echo ""
    echo "[System] Local environment loaded."
    echo "[System] Dependencies verified."
    echo ""
fi

# --- SELF-HEALING: Check if app files exist, download if missing ---
if [ ! -f "main.py" ]; then
    echo "[System] App source code missing. Fetching from GitHub..."
    curl -L -o app_code.zip "$GITHUB_ZIP_URL" --silent
    if [ -f "app_code.zip" ]; then
        tar -xf app_code.zip
        if [ -d "$GITHUB_EXTRACT_FOLDER" ]; then
            # Prevent the script from overwriting the Mac launcher file
            rm -f "$GITHUB_EXTRACT_FOLDER/Launch_Dashboard.command" 2>/dev/null
            
            # Copy all files from the extracted folder to the current directory
            cp -R "$GITHUB_EXTRACT_FOLDER/"* . >/dev/null 2>&1
            rm -rf "$GITHUB_EXTRACT_FOLDER"
            
            # Grant execute permissions to any new Mac batch scripts pulled from the repo
            chmod +x *.command 2>/dev/null
        fi
        rm -f app_code.zip
        echo "[System] App code successfully downloaded."
    else
        echo "[ERROR] Failed to download app files. Please check your internet connection."
        read -p "Press Enter to exit..."
        exit 1
    fi
fi

echo "Launching MotoRater Dashboard..."
sleep 2

# --- Launch App ---
"$STREAMLIT_EXE" run main.py
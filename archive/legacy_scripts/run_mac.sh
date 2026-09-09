#!/bin/bash

# ==========================================
#      MOTO-RATER DASHBOARD LAUNCHER
#         (macOS & Linux Edition)
# ==========================================

VENV_DIR="venv"
MARKER_FILE="$VENV_DIR/.installed"
LOG_FILE="install_log.txt"

# --- Helper Function: Draw Progress ---
draw_progress() {
    clear
    echo "=================================================="
    echo "     	      MOTO-RATER DASHBOARD SETUP"
    echo "=================================================="
    echo ""
    echo " $1 Step $2/5"
    echo ""
    echo " Current Task: $3"
    echo ""
    echo " (First time setup: Please wait...)"
    echo "=================================================="
}

# --- 1. Check for Python 3 ---
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed."
    echo "macOS: Please run 'xcode-select --install' or install via Homebrew."
    echo "Linux: Please install python3 (e.g., sudo apt install python3)"
    exit 1
fi

# --- 2. Check/Create Virtual Environment ---
if [ ! -d "$VENV_DIR" ]; then
    clear
    echo "=================================================="
    echo "     First Time Setup: Creating Environment..."
    echo "=================================================="
    python3 -m venv "$VENV_DIR"
    
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create virtual environment."
        echo "Linux Users: You might need to run 'sudo apt install python3-venv'"
        exit 1
    fi
fi

# --- 3. Activate Environment ---
source "$VENV_DIR/bin/activate"

# --- 4. SMART CHECK: Are dependencies already installed? ---
if [ -f "$MARKER_FILE" ]; then
    # === FAST LANE ===
    clear
    echo "=================================================="
    echo "     		 MOTO-RATER DASHBOARD"
    echo "=================================================="
    echo ""
    echo " [System] Environment loaded."
    echo " [System] Dependencies verified."
    echo ""
    echo " Launching App..."
    sleep 1
    streamlit run app.py
    exit 0
fi

# === SLOW LANE (First Run Only) ===

# Define Progress Bars
BAR1="[##........]"
BAR2="[####......]"
BAR3="[######....]"
BAR4="[########..]"
BAR5="[##########]"

# Step 1: Upgrade Pip
draw_progress "$BAR1" "1" "Upgrading Pip (Core Installer)"
pip install --upgrade pip --quiet > "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed. See details:"
    cat "$LOG_FILE"
    exit 1
fi

# Step 2: Install Pandas
draw_progress "$BAR2" "2" "Installing Pandas (Data Engine)"
pip install pandas --quiet >> "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed. See details:"
    cat "$LOG_FILE"
    exit 1
fi

# Step 3: Install Openpyxl
draw_progress "$BAR3" "3" "Installing Openpyxl (Excel Reader)"
pip install openpyxl --quiet >> "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed. See details:"
    cat "$LOG_FILE"
    exit 1
fi

# Step 4: Install Plotly
draw_progress "$BAR4" "4" "Installing Plotly (Charting Engine)"
pip install plotly --quiet >> "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed. See details:"
    cat "$LOG_FILE"
    exit 1
fi

# Step 5: Install Streamlit
draw_progress "$BAR5" "5" "Installing Streamlit (App Framework)"
pip install streamlit --quiet >> "$LOG_FILE" 2>&1
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed. See details:"
    cat "$LOG_FILE"
    exit 1
fi

# --- 5. Create Marker & Cleanup ---
touch "$MARKER_FILE"
if [ -f "$LOG_FILE" ]; then
    rm "$LOG_FILE"
fi

clear
echo "=================================================="
echo " $BAR5 100% - Installation Complete"
echo "=================================================="
echo ""
echo " Launching MotoRater Dashboard..."
sleep 2

streamlit run app.py
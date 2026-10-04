#!/usr/bin/env bash

cd "$(dirname "$0")"

get_python() {
    if command -v python3 &>/dev/null; then
        echo "python3"
    elif command -v python &>/dev/null; then
        echo "python"
    else
        echo ""
    fi
}

PY_CMD=$(get_python)

if [ -z "$PY_CMD" ]; then
    echo "[!] Python runtime was not found on your system."
    read -p "Would you like to install Python now? (y/n): " INSTALL_CHOICE
    
    if [[ "$INSTALL_CHOICE" =~ ^[Yy]$ ]]; then
        echo ""
        if [[ "$OSTYPE" == "darwin"* ]]; then
            if command -v brew &>/dev/null; then
                echo "Installing Python 3 via Homebrew..."
                brew install python
            else
                echo "[!] Homebrew is not installed. Please install Python from https://www.python.org/downloads/macos/"
                exit 1
            fi
        elif command -v apt &>/dev/null; then
            sudo apt update && sudo apt install -y python3
        elif command -v dnf &>/dev/null; then
            sudo dnf install -y python3
        elif command -v pacman &>/dev/null; then
            sudo pacman -S --noconfirm python
        else
            echo "[!] Package manager not recognized. Please install Python 3 manually."
            exit 1
        fi
        
        PY_CMD=$(get_python)
        if [ -z "$PY_CMD" ]; then
            echo "[!] Installation completed, but Python executable was not detected. Please restart your terminal."
            exit 1
        fi
    else
        echo "Cannot proceed without Python runtime. Exiting..."
        exit 1
    fi
fi

# 2. Execute the Python script directly
"$PY_CMD" "sources/android_img_extractor/android_img_extractor.py" "$@"

read -p "Press Enter to exit..."
#!/data/data/com.termux/files/usr/bin/bash
# mcmanage installer
# One-liner: curl -sL https://raw.githubusercontent.com/Kaedo17/msm-webconsole-termux/main/install.sh | bash
# Or: pkg install git && git clone https://github.com/Kaedo17/msm-webconsole-termux && cd msm-webconsole-termux && ./install.sh

INSTALL_DIR="$HOME/.local/bin"
REPO_URL="https://raw.githubusercontent.com/Kaedo17/msm-webconsole-termux/main"

echo "==> mcmanage — Minecraft Server Manager Installer"
echo

# ── Detect Termux ──
if [ ! -d /data/data/com.termux ]; then
    echo "[!] This installer is for Termux on Android only."
    exit 1
fi

echo "[1/5] Updating packages..."
pkg update -y

echo "[2/5] Installing dependencies..."
pkg install openjdk-17 screen curl python -y

echo "[3/5] Installing Flask for web UI..."
pip install flask 2>/dev/null || python3 -m pip install flask 2>/dev/null

echo "[4/5] Installing mcmanage.sh + webconsole.py..."
mkdir -p "$INSTALL_DIR"

# Try local files first (if install.sh is in the repo directory)
SCRIPT_SRC="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"
if [ -f "$SCRIPT_SRC/mcmanage.sh" ] && [ -f "$SCRIPT_SRC/webconsole.py" ]; then
    echo "   (copying local files)"
    cp "$SCRIPT_SRC/mcmanage.sh" "$INSTALL_DIR/mcmanage" || exit 1
    cp "$SCRIPT_SRC/webconsole.py" "$INSTALL_DIR/webconsole.py" || exit 1
else
    echo "   (downloading from GitHub)"
    DOWNLOAD_OK=false

    # Try with curl (up to 3 attempts)
    for i in 1 2 3; do
        echo "   Attempt $i/3..."
        if curl -sSfLo "$INSTALL_DIR/mcmanage" "$REPO_URL/mcmanage.sh" 2>/dev/null &&
           curl -sSfLo "$INSTALL_DIR/webconsole.py" "$REPO_URL/webconsole.py" 2>/dev/null; then
            DOWNLOAD_OK=true
            break
        fi
        [ $i -lt 3 ] && sleep 2
    done

    # Fallback: try wget if curl failed
    if ! $DOWNLOAD_OK; then
        echo "   curl failed, trying wget..."
        for i in 1 2 3; do
            echo "   Attempt $i/3..."
            if wget -qO "$INSTALL_DIR/mcmanage" "$REPO_URL/mcmanage.sh" 2>/dev/null &&
               wget -qO "$INSTALL_DIR/webconsole.py" "$REPO_URL/webconsole.py" 2>/dev/null; then
                DOWNLOAD_OK=true
                break
            fi
            [ $i -lt 3 ] && sleep 2
        done
    fi

    if ! $DOWNLOAD_OK; then
        echo
        echo "[!] Download from GitHub failed."
        echo "[!] This may be a network issue or raw.githubusercontent.com may be blocked."
        echo
        echo "Try one of these instead:"
        echo ""
        echo "  Method 1 — Git clone (recommended):"
        echo "    pkg install git"
        echo "    git clone https://github.com/Kaedo17/msm-webconsole-termux"
        echo "    cd msm-webconsole-termux"
        echo "    ./install.sh"
        echo ""
        echo "  Method 2 — Download ZIP from browser:"
        echo "    1. Open https://github.com/Kaedo17/msm-webconsole-termux"
        echo "    2. Click Code > Download ZIP"
        echo "    3. Extract and run ./install.sh"
        echo ""
        echo "  Method 3 — Manual setup:"
        echo "    Copy mcmanage.sh and webconsole.py next to install.sh"
        echo "    Then run: ./install.sh"
        exit 1
    fi
fi

chmod +x "$INSTALL_DIR/mcmanage"

echo "[5/5] Verifying..."
if [ -f "$INSTALL_DIR/mcmanage" ]; then
    echo "[OK] Installed to $INSTALL_DIR/mcmanage"
    echo "[OK] Web UI at  $INSTALL_DIR/webconsole.py"
else
    echo "[!] Install failed."
    exit 1
fi

# ── Auto-add to PATH ──
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo
    echo "Adding $INSTALL_DIR to PATH in ~/.bashrc..."
    mkdir -p "$HOME"
    touch "$HOME/.bashrc"
    if ! grep -qF 'export PATH="$HOME/.local/bin:$PATH"' "$HOME/.bashrc" 2>/dev/null; then
        echo >> "$HOME/.bashrc"
        echo "# mcmanage" >> "$HOME/.bashrc"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$HOME/.bashrc"
        echo "[OK] Added to ~/.bashrc"
    fi
    export PATH="$HOME/.local/bin:$PATH"
    echo "[OK] Run 'source ~/.bashrc' or restart Termux for PATH to persist."
fi

echo
echo "=============================="
echo "  Installation complete!"
echo "=============================="
echo
echo "Quick start:"
echo "  cd ~/minecraft-server"
echo "  mcmanage init"
echo
echo "Web dashboard:"
echo "  mcmanage web"
echo
echo "Use existing server:"
echo "  mcmanage --dir /path/to/your/server start"
echo

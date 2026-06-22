#!/data/data/com.termux/files/usr/bin/bash
# mcmanage installer
# One-liner: curl -sL https://raw.githubusercontent.com/Kaedo17/msm-webconsole-termux/main/install.sh | bash

INSTALL_DIR="$HOME/.local/bin"
REPO_URL="https://raw.githubusercontent.com/Kaedo17/msm-webconsole-termux/main"

echo "==> mcmanage — Minecraft Server Manager Installer"
echo

# ── Detect Termux ──
if [ ! -d /data/data/com.termux ]; then
    echo "[!] This installer is for Termux on Android only."
    exit 1
fi

# ── Detect if running locally or via pipe ──
SCRIPT_SRC="$(cd "$(dirname "$0")" 2>/dev/null && pwd)"

echo "[1/5] Updating packages..."
pkg update -y

echo "[2/5] Installing dependencies..."
pkg install openjdk-17 screen curl python -y

echo "[3/5] Installing Flask for web UI..."
pip install flask 2>/dev/null || python3 -m pip install flask 2>/dev/null

echo "[4/5] Installing mcmanage.sh + webconsole.py..."
mkdir -p "$INSTALL_DIR"

# If running locally and files exist beside install.sh, copy them
if [ -f "$SCRIPT_SRC/mcmanage.sh" ] && [ -f "$SCRIPT_SRC/webconsole.py" ]; then
    echo "   (copying local files)"
    cp "$SCRIPT_SRC/mcmanage.sh" "$INSTALL_DIR/mcmanage"
    cp "$SCRIPT_SRC/webconsole.py" "$INSTALL_DIR/webconsole.py"
else
    echo "   (downloading from GitHub)"
    curl -sLo "$INSTALL_DIR/mcmanage" "$REPO_URL/mcmanage.sh" || {
        echo "[!] Download failed — make sure https://github.com/Kaedo17/msm-webconsole-termux has the files"
        echo "    or copy the files manually next to install.sh and run it locally."
        exit 1
    }
    curl -sLo "$INSTALL_DIR/webconsole.py" "$REPO_URL/webconsole.py"
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

# ── PATH check ──
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo
    echo "[!] Add $INSTALL_DIR to your PATH in ~/.bashrc:"
    echo "    export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo "    Then: source ~/.bashrc"
fi

echo
echo "=============================="
echo "  Installation complete!"
echo "=============================="
echo
echo "Ready to play:"
echo "  cd ~/minecraft-server"
echo "  mcmanage init"
echo
echo "Web dashboard:"
echo "  mcmanage web"
echo

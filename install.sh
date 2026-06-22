#!/data/data/com.termux/files/usr/bin/bash
# mcmanage installer — one-liner: curl -sL https://tinyurl.com/XXX | bash

set -e

REPO_URL="https://raw.githubusercontent.com/YOUR_USER/mcmanage/main"
INSTALL_DIR="$HOME/.local/bin"
TARGET="$INSTALL_DIR/mcmanage"
WEB_PY="$INSTALL_DIR/webconsole.py"

echo "==> mcmanage — Minecraft Server Manager Installer"
echo

# Detect Termux
if [ ! -d /data/data/com.termux ]; then
    echo "[!] This installer is for Termux on Android."
    echo "    Visit https://termux.com to install Termux first."
    exit 1
fi

echo "[1/5] Updating packages..."
pkg update -y

echo "[2/5] Installing dependencies (openjdk-17, screen, curl, python)..."
pkg install openjdk-17 screen curl python -y

echo "[3/5] Downloading mcmanage.sh + webconsole.py..."
mkdir -p "$INSTALL_DIR"
curl -sLo "$TARGET" "$REPO_URL/mcmanage.sh"
chmod +x "$TARGET"
curl -sLo "$WEB_PY" "$REPO_URL/webconsole.py"

echo "[4/5] Installing Flask for web UI..."
pip install flask 2>/dev/null || python3 -m pip install flask 2>/dev/null

echo "[5/5] Verifying installation..."
if command -v mcmanage &>/dev/null || [ -f "$TARGET" ]; then
    echo "[OK] Installed to $TARGET"
else
    echo "[!] Installation failed."
    exit 1
fi

# Ensure INSTALL_DIR is in PATH
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo
    echo "[!] $INSTALL_DIR is not in your PATH."
    echo "    Add this to ~/.bashrc:"
    echo "      export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo "    Then reload: source ~/.bashrc"
fi

echo
echo "=============================="
echo "  Installation complete!"
echo "=============================="
echo
echo "Quick start (inside your server directory):"
echo "  mcmanage init"
echo
echo "Web dashboard:"
echo "  mcmanage web"
echo "  # or: python3 webconsole.py --dir /path/to/server"
echo
echo "Or manually:"
echo "  mkdir -p ~/minecraft-server && cd ~/minecraft-server"
echo "  mcmanage install"
echo "  echo 'eula=true' > eula.txt"
echo "  mcmanage start"
echo "  mcmanage console"
echo

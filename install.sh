#!/data/data/com.termux/files/usr/bin/bash
# mcmanage installer
# One-liner: curl -sL https://raw.githubusercontent.com/Kaedo17/msm-webconsole-termux/main/install.sh | bash
# Or: git clone https://github.com/Kaedo17/msm-webconsole-termux && cd msm-webconsole-termux && ./install.sh

INSTALL_DIR="$HOME/.local/bin"
REPO_URL="https://raw.githubusercontent.com/Kaedo17/msm-webconsole-termux/main"

echo "==> mcmanage — Minecraft Server Manager Installer"
echo

if [ ! -d /data/data/com.termux ]; then
    echo "[!] This installer is for Termux on Android only."
    exit 1
fi

# ── Resolve this script's real directory (handles symlinks) ──
SCRIPT_FILE="$(readlink -f "$0" 2>/dev/null || realpath "$0" 2>/dev/null || echo "$0")"
SCRIPT_DIR="$(dirname "$SCRIPT_FILE")"

echo "   Installer dir: $SCRIPT_DIR"
echo "   Target dir:    $INSTALL_DIR"

# ── Clean old files (remove both files and broken symlinks) ──
rm -f "$INSTALL_DIR/mcmanage" "$INSTALL_DIR/webconsole.py" 2>/dev/null
# Also clean any directory with the same name (broken state from previous runs)
[ -d "$INSTALL_DIR/mcmanage" ] && rm -rf "$INSTALL_DIR/mcmanage" 2>/dev/null
[ -d "$INSTALL_DIR/webconsole.py" ] && rm -rf "$INSTALL_DIR/webconsole.py" 2>/dev/null

echo "[1/5] Updating packages..."
pkg update -y

echo "[2/5] Installing dependencies..."
pkg install openjdk-17 screen curl python -y

echo "[3/5] Installing Flask for web UI..."
pip install flask 2>/dev/null || python3 -m pip install flask 2>/dev/null

echo "[4/5] Installing mcmanage.sh + webconsole.py..."
mkdir -p "$INSTALL_DIR"

# Try local files first (if install.sh is in the repo directory)
LOCAL_OK=false
if [ -f "$SCRIPT_DIR/mcmanage.sh" ] && [ -f "$SCRIPT_DIR/webconsole.py" ]; then
    echo "   Found local files in: $SCRIPT_DIR"
    echo "   Copying..."
    cp -f "$SCRIPT_DIR/mcmanage.sh" "$INSTALL_DIR/mcmanage" && \
    cp -f "$SCRIPT_DIR/webconsole.py" "$INSTALL_DIR/webconsole.py" && \
    LOCAL_OK=true
fi

if ! $LOCAL_OK; then
    echo "   Downloading from GitHub..."
    DOWNLOAD_OK=false
    for i in 1 2 3; do
        echo "   Attempt $i/3..."
        if curl -sSfLo "$INSTALL_DIR/mcmanage" "$REPO_URL/mcmanage.sh" 2>/dev/null &&
           curl -sSfLo "$INSTALL_DIR/webconsole.py" "$REPO_URL/webconsole.py" 2>/dev/null; then
            DOWNLOAD_OK=true
            break
        fi
        [ $i -lt 3 ] && sleep 2
    done
    if ! $DOWNLOAD_OK; then
        echo
        echo "[!] Download from GitHub failed."
        echo
        echo "Try the git clone method instead:"
        echo "  pkg install git"
        echo "  git clone https://github.com/Kaedo17/msm-webconsole-termux"
        echo "  cd msm-webconsole-termux"
        echo "  ./install.sh"
        echo
        echo "Or download the ZIP from:"
        echo "  https://github.com/Kaedo17/msm-webconsole-termux"
        exit 1
    fi
fi

chmod +x "$INSTALL_DIR/mcmanage"

echo "[5/5] Verifying..."
if [ -f "$INSTALL_DIR/mcmanage" ]; then
    echo "[OK] Installed to $INSTALL_DIR/mcmanage"
    echo "[OK] Web UI at  $INSTALL_DIR/webconsole.py"
else
    echo "[!] Install failed — $INSTALL_DIR/mcmanage not found."
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
    echo "[OK] Now 'mcmanage' works in this session."
    echo "    Run 'source ~/.bashrc' or restart Termux to make permanent."
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
echo "Update:"
echo "  cd msm-webconsole-termux && git pull && ./install.sh"
echo

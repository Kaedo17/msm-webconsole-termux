#!/data/data/com.termux/files/usr/bin/bash
# mcmanage installer
# One-liner: curl -sL https://raw.githubusercontent.com/Kaedo17/msm-webconsole-termux/main/install.sh | bash
# Or: git clone https://github.com/Kaedo17/msm-webconsole-termux && cd msm-webconsole-termux && ./install.sh

INSTALL_DIR="$HOME/.local/bin"
REPO_URL="https://raw.githubusercontent.com/Kaedo17/msm-webconsole-termux/main"
THIS_DIR="$(dirname "$(readlink -f "$0" 2>/dev/null || realpath "$0" 2>/dev/null || echo "$0")")"

echo "==> mcmanage — Minecraft Server Manager Installer"
echo

if [ ! -d /data/data/com.termux ]; then
    echo "[!] This installer is for Termux on Android only."
    exit 1
fi

echo "  Source: $THIS_DIR"
echo "  Target: $INSTALL_DIR"
echo

# ── Clean destination thoroughly ──
mkdir -p "$INSTALL_DIR"
for name in mcmanage webconsole.py; do
    target="$INSTALL_DIR/$name"
    # Remove whatever is there: file, dir, broken symlink
    rm -f "$target" 2>/dev/null
    rm -rf "$target" 2>/dev/null
    [ -L "$target" ] && unlink "$target" 2>/dev/null
    [ -e "$target" ] && rm -rf "$target" 2>/dev/null
done

echo "[1/5] Updating packages..."
pkg update -y

echo "[2/5] Installing dependencies..."
pkg install openjdk-17 screen curl python -y

echo "[3/5] Installing Flask for web UI..."
pip install flask 2>/dev/null || python3 -m pip install flask 2>/dev/null

echo "[4/5] Installing mcmanage.sh + webconsole.py + modules..."

MODULES="mc_state.py mc_helpers.py mc_properties.py mc_modrinth.py mc_curseforge.py mc_server.py mc_routes.py mc_instances.py mc_downloads.py mc_playit.py"
INSTALL_OK=false

# Try local files
if [ -f "$THIS_DIR/mcmanage.sh" ] && [ -f "$THIS_DIR/webconsole.py" ]; then
    echo "   Copying local files from $THIS_DIR ..."
    cat "$THIS_DIR/mcmanage.sh" > "$INSTALL_DIR/mcmanage" || INSTALL_OK=false
    cat "$THIS_DIR/webconsole.py" > "$INSTALL_DIR/webconsole.py" || INSTALL_OK=false
    for mod in $MODULES; do
        if [ -f "$THIS_DIR/$mod" ]; then
            cat "$THIS_DIR/$mod" > "$INSTALL_DIR/$mod" || INSTALL_OK=false
        fi
    done
    INSTALL_OK=true
fi

# Fallback to GitHub download
if ! $INSTALL_OK; then
    echo "   Downloading from GitHub..."
    for i in 1 2 3; do
        echo "   Attempt $i/3..."
        INSTALL_OK=true
        curl -sSfLo "$INSTALL_DIR/mcmanage" "$REPO_URL/mcmanage.sh" 2>/dev/null || INSTALL_OK=false
        curl -sSfLo "$INSTALL_DIR/webconsole.py" "$REPO_URL/webconsole.py" 2>/dev/null || INSTALL_OK=false
        for mod in $MODULES; do
            curl -sSfLo "$INSTALL_DIR/$mod" "$REPO_URL/$mod" 2>/dev/null || INSTALL_OK=false
        done
        $INSTALL_OK && break
        sleep 2
    done
fi

if ! $INSTALL_OK; then
    echo
    echo "[!] Installation failed."
    echo "    Could not copy local files or download from GitHub."
    echo
    echo "Try:"
    echo "  pkg install git"
    echo "  git clone https://github.com/Kaedo17/msm-webconsole-termux"
    echo "  cd msm-webconsole-termux"
    echo "  ./install.sh"
    exit 1
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
    line='export PATH="$HOME/.local/bin:$PATH"'
    if ! grep -qF "$line" "$HOME/.bashrc" 2>/dev/null; then
        echo "" >> "$HOME/.bashrc"
        echo "# mcmanage" >> "$HOME/.bashrc"
        echo "$line" >> "$HOME/.bashrc"
        echo "[OK] Added to ~/.bashrc"
    fi
    export PATH="$HOME/.local/bin:$PATH"
    echo "[OK] Run 'source ~/.bashrc' or restart Termux to make permanent."
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
echo "Update:"
echo "  cd msm-webconsole-termux && git pull && ./install.sh"
echo

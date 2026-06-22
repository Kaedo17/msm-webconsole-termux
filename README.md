# mcmanage — Minecraft Java Server Manager for Termux

Run a full Minecraft Java server on your Android phone via Termux, with a web dashboard.

## Features

- **One-command setup** — installs everything and starts the server
- **Web Dashboard** — manage via browser at `http://localhost:5000`
- **Start / Stop / Restart** with graceful player countdown
- **Live console** — see output + send commands from browser or terminal
- **File Manager** — edit server.properties, eula.txt from browser
- **World backups** — create & restore with auto-prune
- **Optimize** — applies performance tweaks for Android
- **PATH access** — run `mcmanage` from anywhere

## Install

### Option A — One-liner

```bash
curl -sL https://raw.githubusercontent.com/Kaedo17/msm-webconsole-termux/main/install.sh | bash
```

### Option B — Manual (files already on your device)

Copy `mcmanage.sh`, `webconsole.py`, and `install.sh` to Termux, then:

```bash
chmod +x install.sh
./install.sh
```

The installer will:
1. Install openjdk-17, screen, curl, python
2. Install Flask (for web UI)
3. Copy scripts to `~/.local/bin/mcmanage` and `~/.local/bin/webconsole.py`
4. Check that `~/.local/bin` is in PATH

## Usage

```bash
# Use an existing server folder
mcmanage --dir /path/to/existing/server start

# Full setup — install deps, download server jar, accept EULA, start, console
mcmanage init

# Web dashboard (open http://localhost:5000 in browser)
mcmanage web

# Manual control
mcmanage --dir ~/minecraft-server start
mcmanage stop 15
mcmanage restart
mcmanage console          # Ctrl+A then D to detach
mcmanage cmd "say hello"

# Server info
mcmanage status
mcmanage logs 50
mcmanage watch

# Backups
mcmanage backup
mcmanage backups

# Files
mcmanage props            # edit server.properties
mcmanage optimize         # apply tweaks
```

## Web Dashboard

Open `http://localhost:5000` after running `mcmanage web`.

- Start / Stop / Restart the server
- Live console log with command input
- File browser and editor (server.properties, eula.txt, etc.)
- One-click world backups

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_DIR` | current directory | Server folder |
| `SERVER_JAR` | `server.jar` | Jar filename |
| `MAX_RAM` | `2G` | Max heap size |
| `MAX_BACKUPS` | `7` | Backups to keep |
| `LOG_FILE` | `$SERVER_DIR/server.log` | Log path |

```bash
MAX_RAM=3G mcmanage start
```

## Tips

- **Detach from console:** `Ctrl+A` then `D`
- **Increase RAM:** Set `MAX_RAM=4G` if your device has enough memory
- **Keep alive:** Use `termux-wake-lock` to keep the server running in background
- **Auto-start:** `mcmanage service` sets up termux-services

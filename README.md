# mcmanage — Minecraft Java Server Manager for Termux

Run a full Minecraft Java server on your Android phone via Termux.

## Features

- **One-command setup** — installs everything and starts the server
- **Web Dashboard** — manage via browser at `http://localhost:5000`
- **Full lifecycle** — start/stop/restart with graceful shutdown
- **Screen console** — attach/detach server terminal
- **World backups** — auto-prunes old backups
- **Logs** — tail live or view recent output
- **File Manager** — edit server.properties, eula.txt from browser
- **Optimize** — applies performance tweaks for Android
- **Service** - termux-services integration
- **PATH access** — symlink to run from anywhere

## Requirements

- [Termux](https://f-droid.org/repo/com.termux.fdroid.apk) (F-Droid version recommended)
- Storage permission: `termux-setup-storage`
- ~2.5 GB free space (server + world)

## Quick Install

```bash
curl -sL https://raw.githubusercontent.com/Kaedo17/mcmanage/main/mcmanage.sh -o mcmanage.sh
chmod +x mcmanage.sh
./mcmanage.sh init
```

## Manual Setup

```bash
pkg update && pkg upgrade -y
pkg install openjdk-17 screen curl -y
chmod +x mcmanage.sh
echo 'eula=true' > eula.txt
./mcmanage.sh start
./mcmanage.sh console   # Ctrl+A then D to detach
```

## Add to PATH

```bash
./mcmanage.sh link
```

Then use `mcmanage` from any directory.

## Commands

| Command | Description |
|---------|-------------|
| `init` | Full setup: install deps, download jar, accept EULA, start & console |
| `link` | Symlink to `~/.local/bin/mcmanage` for global access |
| `start` | Start the server in a screen session |
| `stop [sec]` | Graceful stop with countdown (default 30s) |
| `restart [sec]` | Restart with optional shutdown warning |
| `console` | Attach to server console (Ctrl+A D to detach) |
| `cmd <cmd>` | Send a command (e.g. `cmd say hi`, `cmd whitelist add Steve`) |
| `status` | Show PID, memory usage, and uptime |
| `backup` | Backup all world directories |
| `backups` | List available backups |
| `restore <file>` | Restore world from a backup archive |
| `logs [n]` | Show last N log lines (default 50) |
| `watch` | Follow logs in real-time |
| `props` | Edit `server.properties` |
| `optimize` | Apply Android-friendly performance tweaks |
| `install` | Download Paper / Purpur / Vanilla server jar |
| `web` | Launch web dashboard (Python Flask UI) |
| `service` | Create a termux-services entry for autostart |
| `help` | Show usage info |

## Configuration

Set via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `SERVER_DIR` | script directory | Server folder |
| `SERVER_JAR` | `server.jar` | Jar filename |
| `MAX_RAM` | `2G` | Max heap size |
| `MAX_BACKUPS` | `7` | Backups to retain |
| `LOG_FILE` | `$SERVER_DIR/server.log` | Log file path |

## Web Dashboard

A full browser-based management UI (`webconsole.py`) is included alongside `mcmanage.sh`.

```bash
./mcmanage.sh web
# or directly:
python3 webconsole.py --dir /path/to/server --port 5000
```

Open `http://localhost:5000` in your browser to:

- **Start / Stop / Restart** the server
- **Live console** — see output in real-time, send commands
- **File Manager** — browse and edit server files (server.properties, etc.)
- **Backups** — create and restore world backups from the browser
- **Dashboard** — view memory, uptime, player count

Flask is auto-installed on first run via `pip`.

Example:

```bash
MAX_RAM=3G ./mcmanage.sh start
```

## Tips

- **Detach from console:** `Ctrl+A` then `D`
- **Increase RAM:** Set `MAX_RAM=4G` if your device has enough memory
- **Port forwarding:** Use `termux-wake-lock` to keep the server alive in background; forward port 25565 in your router
- **Auto-start:** `./mcmanage.sh service` sets up a termux-service

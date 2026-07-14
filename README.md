# Minecraft Web Manager

A full-featured Minecraft server manager with a web dashboard and desktop app.  
Run on **Termux (Android)** via CLI or **Windows** as a native desktop app.

## Features

- **Server Lifecycle** — Start / Stop / Restart with graceful player countdown
- **Live Console** — Real-time output with command input
- **Player Management** — Whitelist, ban, op/deop, kick, remove — all from the UI
- **File Manager** — Edit server.properties, eula.txt, mod configs from the browser
- **Mod & Pack Installer** — Browse and install mods from Modrinth & CurseForge
- **World Backups** — Create & restore with one click
- **Playit.gg Tunnel** — Share your server online without port forwarding
- **Multi-Server** — Manage multiple server instances from one dashboard
- **Auto Java** — Auto-downloads the correct Java version per Minecraft version (8/11/17/21)
- **RAM Controls** — Adjust min/max RAM from the dashboard
- **Properties Editor** — Visual editor for server.properties

## Windows Desktop App

### Download

Download the latest release from the [Releases page](https://github.com/Kaedo17/msm-webconsole-termux/releases).

Or build it yourself:
```bash
# Requirements: Python 3.10+, PyInstaller
pip install flask pywebview pyinstaller
python build_exe.py
```

The EXE will be at `dist/MinecraftWebManager/MinecraftWebManager.exe`.

### Installer

Install [NSIS](https://nsis.sourceforge.io/) and run:
```bash
python build_exe.py --installer
```

The installer supports:
- Choose install directory (default: `C:\Program Files\MinecraftWebManager`)
- Start Menu & Desktop shortcuts
- Windows Add/Remove Programs
- Update detection (re-running the installer updates the app)

### Usage

1. Run `MinecraftWebManager.exe`
2. Click **Create Server** — pick a name, version, and server type
3. The app downloads the server jar automatically
4. Click **Start** to launch the server
5. Open the **Players** tab to manage whitelist, bans, and operators

#### Java Auto-Install

If Java isn't installed on your system:
- The dashboard shows a **Download & Install Java** button
- Choose Java 8, 11, 17, or 21 depending on your Minecraft version
- The app downloads Eclipse Temurin JDK and configures it automatically
- When starting a server, if the required Java version is missing, it auto-downloads the right one

#### Tunnel Setup

1. Go to the **Tunnel** tab
2. Download playit.gg from [playit.gg/download](https://playit.gg/download)
3. Run `playit.exe` once to sign in and claim your account
4. Close playit.exe, relaunch the app, click **Start Daemon**

## Termux / Android

### Install

```bash
pkg install git
git clone https://github.com/Kaedo17/msm-webconsole-termux
cd msm-webconsole-termux
chmod +x install.sh
./install.sh
```

Or one-liner:
```bash
curl -sL https://raw.githubusercontent.com/Kaedo17/msm-webconsole-termux/main/install.sh | bash
```

### Usage

```bash
# Start a server
mcmanage --dir ~/minecraft-server start

# Web dashboard (open http://localhost:5000 in browser)
mcmanage web

# Or use the Python web server directly
python webconsole.py --port 5000
```

## Screenshots

| Dashboard | Players | Console |
|-----------|---------|---------|
| Status cards, RAM control, Java info | Whitelist, ban, op with badges | Live output & commands |

## Configuration

### Web Console
| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `5000` | Web UI port |
| `HOST` | `0.0.0.0` | Bind address |

### Environment Variables
| Variable | Description |
|----------|-------------|
| `JAVA_HOME` | Custom Java installation path |
| `PORT` | Web UI port override |
| `HOST` | Bind address override |

## Development

```bash
# Run from source
pip install flask
python webconsole.py --port 5000

# Desktop app from source
pip install flask pywebview
python mc_app.py
```

## License

MIT

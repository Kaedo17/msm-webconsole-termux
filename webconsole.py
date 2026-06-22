#!/data/data/com.termux/files/usr/bin/python3
"""
webconsole.py — Minecraft Web Manager for Termux
Usage:  python webconsole.py [--dir /path/to/server] [--port 5000]
"""

import argparse
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

try:
    from flask import Flask, jsonify, request, Response
except ImportError:
    print("Installing Flask...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "flask"])
    from flask import Flask, jsonify, request, Response

# ── Config ────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
SERVER_DIR = Path(os.environ.get("SERVER_DIR", SCRIPT_DIR))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 5000))
JAVA_BIN = shutil.which("java") or "java"
JAR_NAME = os.environ.get("SERVER_JAR", "server.jar")

# ── Globals ───────────────────────────────────────────────────────────
app = Flask(__name__)
server_proc = None
console_history = []
status_cache = {"online": False, "players": [], "tps": 0, "uptime": 0, "mem_mb": 0, "started_at": ""}
_status_lock = threading.Lock()
CONSOLE_MAX = 500
CONFIG_FILE = None  # set after SERVER_DIR is finalized
MIN_RAM = os.environ.get("MIN_RAM", "512M")
MAX_RAM = os.environ.get("MAX_RAM", "2G")

# ── Config persistence ───────────────────────────────────────────────

def config_path():
    return SERVER_DIR / ".webconsole.json"

def load_config():
    global MIN_RAM, MAX_RAM
    cf = config_path()
    if cf.exists():
        try:
            d = json.loads(cf.read_text())
            MIN_RAM = d.get("min_ram", MIN_RAM)
            MAX_RAM = d.get("max_ram", MAX_RAM)
        except Exception:
            pass

def save_config():
    cf = config_path()
    try:
        d = {"min_ram": MIN_RAM, "max_ram": MAX_RAM}
        if cf.exists():
            try:
                old = json.loads(cf.read_text())
                d.update(old)
            except Exception:
                pass
        d["min_ram"] = MIN_RAM
        d["max_ram"] = MAX_RAM
        cf.write_text(json.dumps(d, indent=2))
    except Exception:
        pass

# ── Server properties schema ─────────────────────────────────────────

PROPS_SCHEMA = {
    "online-mode":           {"type": "bool",   "cat": "server",   "label": "Online Mode",       "desc": "Authenticate players with Mojang"},
    "difficulty":            {"type": "enum",   "cat": "gameplay", "label": "Difficulty",         "desc": "Game difficulty", "opts": ["peaceful","easy","normal","hard"]},
    "gamemode":              {"type": "enum",   "cat": "gameplay", "label": "Default Gamemode",   "desc": "Default game mode for new players", "opts": ["survival","creative","adventure","spectator"]},
    "pvp":                   {"type": "bool",   "cat": "gameplay", "label": "PvP",               "desc": "Allow player versus player combat"},
    "hardcore":              {"type": "bool",   "cat": "gameplay", "label": "Hardcore",           "desc": "Ban on death"},
    "enable-command-block":  {"type": "bool",   "cat": "server",   "label": "Command Blocks",    "desc": "Enable command blocks"},
    "spawn-monsters":        {"type": "bool",   "cat": "world",    "label": "Spawn Monsters",     "desc": "Natural monster spawning"},
    "spawn-animals":         {"type": "bool",   "cat": "world",    "label": "Spawn Animals",      "desc": "Natural animal spawning"},
    "spawn-npcs":            {"type": "bool",   "cat": "world",    "label": "Spawn NPCs",         "desc": "Natural villager spawning"},
    "allow-flight":          {"type": "bool",   "cat": "gameplay", "label": "Allow Flight",       "desc": "Allow flying without cheat"},
    "white-list":            {"type": "bool",   "cat": "server",   "label": "Whitelist",          "desc": "Only whitelisted players can join"},
    "enforce-whitelist":     {"type": "bool",   "cat": "server",   "label": "Enforce Whitelist",  "desc": "Kick non-whitelisted players on reload"},
    "enable-query":          {"type": "bool",   "cat": "network",  "label": "Query",              "desc": "Enable GameSpy query protocol"},
    "enable-rcon":           {"type": "bool",   "cat": "network",  "label": "RCON",               "desc": "Enable remote console access"},
    "broadcast-rcon-to-ops": {"type": "bool",   "cat": "network",  "label": "Broadcast RCON",     "desc": "Broadcast RCON commands to ops"},
    "prevent-proxy-connections":{"type": "bool","cat": "network",  "label": "Prevent Proxy",      "desc": "Block proxy connections"},
    "sync-chunk-writes":     {"type": "bool",   "cat": "world",    "label": "Sync Chunk Writes",  "desc": "Sync world writes to disk"},
    "max-players":           {"type": "number", "cat": "server",   "label": "Max Players",        "desc": "Maximum concurrent players", "min": 1, "max": 100},
    "view-distance":         {"type": "number", "cat": "world",    "label": "View Distance",      "desc": "Client view radius in chunks", "min": 2, "max": 32},
    "simulation-distance":   {"type": "number", "cat": "world",    "label": "Sim Distance",       "desc": "Entity simulation radius", "min": 2, "max": 32},
    "server-port":           {"type": "number", "cat": "network",  "label": "Server Port",        "desc": "Port to listen on", "min": 1, "max": 65535},
    "spawn-protection":      {"type": "number", "cat": "world",    "label": "Spawn Protection",   "desc": "Radius around spawn protected", "min": 0},
    "player-idle-timeout":   {"type": "number", "cat": "server",   "label": "Idle Timeout",       "desc": "Kick idle players after (minutes)", "min": 0},
    "max-world-size":        {"type": "number", "cat": "world",    "label": "Max World Size",     "desc": "World border radius", "min": 1},
    "rate-limit":            {"type": "number", "cat": "network",  "label": "Rate Limit",         "desc": "Packets per second limit", "min": 0},
    "max-tick-time":         {"type": "number", "cat": "server",   "label": "Max Tick Time",      "desc": "Max ms per tick before watchdog", "min": 0},
    "entity-broadcast-range-percentage": {"type": "number", "cat": "world", "label": "Entity Range %", "desc": "Entity tracking range %", "min": 10, "max": 1000},
    "network-compression-threshold": {"type": "number", "cat": "network", "label": "Compression", "desc": "Network compression threshold", "min": -1},
    "motd":                  {"type": "string", "cat": "server",   "label": "MOTD",              "desc": "Message of the Day"},
    "resource-pack":         {"type": "string", "cat": "server",   "label": "Resource Pack URL", "desc": "URL to a resource pack"},
    "resource-pack-sha1":    {"type": "string", "cat": "server",   "label": "Pack SHA1",         "desc": "SHA1 hash of the resource pack"},
    "level-name":            {"type": "string", "cat": "world",    "label": "World Name",        "desc": "World folder name"},
    "level-seed":            {"type": "string", "cat": "world",    "label": "World Seed",        "desc": "Random seed for world generation"},
    "generator-settings":    {"type": "string", "cat": "world",    "label": "Generator Settings", "desc": "Superflat/amplified settings"},
}

def save_props(changes):
    pf = SERVER_DIR / "server.properties"
    if not pf.exists():
        return False, "server.properties not found"
    lines = pf.read_text(encoding="utf-8").splitlines(keepends=True)
    changed = set(changes.keys())
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in changed:
                lines[i] = f"{k}={changes[k]}\n"
                changed.discard(k)
    for k in changed:
        lines.append(f"{k}={changes[k]}\n")
    pf.write_text("".join(lines), encoding="utf-8")
    return True, "Properties saved"

# ── Modrinth helpers ──────────────────────────────────────────────────

MODRINTH_API = "https://api.modrinth.com/v2"

def modrinth_search(query, project_type="modpack", limit=20):
    url = f"{MODRINTH_API}/search?query={urllib.parse.quote(query)}&facets={urllib.parse.quote(json.dumps([[f'project_type:{project_type}']]))}&limit={limit}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mcmanage-termux/1.0"})
        res = urllib.request.urlopen(req, timeout=15)
        data = json.loads(res.read())
        hits = []
        for h in data.get("hits", []):
            hits.append({
                "id": h["project_id"],
                "title": h["title"],
                "description": h.get("description", ""),
                "icon_url": h.get("icon_url", ""),
                "author": h.get("author", ""),
                "downloads": h.get("downloads", 0),
                "slug": h.get("slug", ""),
                "latest_version": h.get("latest_version", ""),
                "project_type": h.get("project_type", project_type),
            })
        return hits
    except Exception as e:
        return {"error": str(e)}

def modrinth_versions(project_id):
    url = f"{MODRINTH_API}/project/{project_id}/version"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "mcmanage-termux/1.0"})
        res = urllib.request.urlopen(req, timeout=15)
        data = json.loads(res.read())
        versions = []
        for v in data:
            versions.append({
                "id": v["id"],
                "name": v["name"],
                "version_number": v["version_number"],
                "game_versions": v.get("game_versions", []),
                "loaders": v.get("loaders", []),
                "files": [{
                    "url": f["url"],
                    "filename": f["filename"],
                    "size": f["size"],
                } for f in v.get("files", [])],
                "date": v.get("date_published", ""),
            })
        return versions
    except Exception as e:
        return {"error": str(e)}

def modrinth_download(file_url, dest_path):
    req = urllib.request.Request(file_url, headers={"User-Agent": "mcmanage-termux/1.0"})
    res = urllib.request.urlopen(req, timeout=60)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        while True:
            chunk = res.read(8192)
            if not chunk:
                break
            f.write(chunk)
    return dest_path

def list_installed_packs():
    mods_dir = SERVER_DIR / "mods"
    rp_dir = SERVER_DIR / "resourcepacks"
    result = []
    for d, pack_type in [(mods_dir, "mod"), (rp_dir, "resourcepack")]:
        if d.exists():
            for f in sorted(d.iterdir()):
                if f.suffix in (".jar", ".zip"):
                    result.append({
                        "name": f.name,
                        "path": str(f.relative_to(SERVER_DIR)),
                        "size": f.stat().st_size,
                        "type": pack_type,
                    })
    return result

# ── Helpers ───────────────────────────────────────────────────────────

def ok(data):
    return jsonify({"ok": True, **data})

def fail(msg, code=400):
    return jsonify({"ok": False, "error": msg}), code

def find_jar():
    jar = SERVER_DIR / JAR_NAME
    if jar.exists():
        return jar
    for f in sorted(SERVER_DIR.glob("*.jar")):
        return f
    return None

def check_eula():
    eula = SERVER_DIR / "eula.txt"
    if not eula.exists():
        eula.write_text("eula=false\n")
        return False
    return "eula=true" in eula.read_text().strip()

def get_props():
    pf = SERVER_DIR / "server.properties"
    if not pf.exists():
        return {}
    props = {}
    for line in pf.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            props[k.strip()] = v.strip()
    return props

def get_proc_mem(pid):
    try:
        out = subprocess.check_output(["ps", "-o", "rss=", "-p", str(pid)], text=True).strip()
        if out:
            return round(int(out) / 1024, 1)
    except Exception:
        pass
    return 0

def get_uptime(pid):
    try:
        out = subprocess.check_output(["ps", "-o", "etime=", "-p", str(pid)], text=True).strip()
        return out
    except Exception:
        return ""

# ── Server Process ────────────────────────────────────────────────────

def server_reader(proc):
    global console_history
    for line in iter(proc.stdout.readline, ""):
        line = line.rstrip("\n\r")
        if not line:
            continue
        console_history.append(line)
        if len(console_history) > CONSOLE_MAX:
            console_history.pop(0)
        # Parse player list from log
        if "]:" in line and "joined the game" in line:
            with _status_lock:
                name = line.split("]:")[-1].strip().split(" ")[0].strip()
                if name and name not in status_cache["players"]:
                    status_cache["players"].append(name)
        if "]:" in line and "left the game" in line:
            with _status_lock:
                name = line.split("]:")[-1].strip().split(" ")[0].strip()
                if name in status_cache["players"]:
                    status_cache["players"].remove(name)

def poll_status():
    global status_cache
    while True:
        with _status_lock:
            running = server_proc is not None and server_proc.poll() is None
            status_cache["online"] = running
            if running and server_proc:
                pid = server_proc.pid
                status_cache["mem_mb"] = get_proc_mem(pid)
                status_cache["uptime"] = get_uptime(pid)
            else:
                status_cache["players"] = []
                status_cache["mem_mb"] = 0
                status_cache["uptime"] = ""
        time.sleep(3)

threading.Thread(target=poll_status, daemon=True).start()

def start_minecraft():
    global server_proc
    if server_proc and server_proc.poll() is None:
        return False, "Server already running."
    jar = find_jar()
    if not jar:
        return False, "No server jar found."
    if not check_eula():
        return False, "EULA not accepted. Edit eula.txt and set eula=true."
    # Generate server.properties on first run
    if not (SERVER_DIR / "server.properties").exists():
        subprocess.run([str(JAVA_BIN), f"-Xms{MIN_RAM}", f"-Xmx{MAX_RAM}", "-jar", str(jar), "--nogui"],
                       cwd=str(SERVER_DIR), capture_output=True, timeout=20)
    cmd = [str(JAVA_BIN), f"-Xms{MIN_RAM}", f"-Xmx{MAX_RAM}", "-jar", str(jar), "--nogui"]
    proc = subprocess.Popen(cmd, cwd=str(SERVER_DIR), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            stdin=subprocess.PIPE, text=True, bufsize=1)
    server_proc = proc
    threading.Thread(target=server_reader, args=(proc,), daemon=True).start()
    with _status_lock:
        status_cache["started_at"] = datetime.now(timezone.utc).isoformat()
        status_cache["online"] = True
    return True, "Server started."

def stop_minecraft(seconds=15):
    global server_proc
    if not server_proc or server_proc.poll() is not None:
        return False, "Server not running."
    proc = server_proc
    # Countdown messages
    for i in range(seconds, 0, -5):
        try:
            proc.stdin.write(f"say §cServer shutdown in {i}s...\n")
            proc.stdin.flush()
            time.sleep(min(5, i))
        except:
            break
    try:
        proc.stdin.write("stop\n")
        proc.stdin.flush()
    except:
        pass
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()
    server_proc = None
    with _status_lock:
        status_cache["online"] = False
    return True, "Server stopped."

def send_minecraft(cmd):
    if not server_proc or server_proc.poll() is not None:
        return False, "Server not running."
    try:
        server_proc.stdin.write(cmd + "\n")
        server_proc.stdin.flush()
        return True, "Command sent."
    except Exception as e:
        return False, str(e)

# ── Web Routes ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return HTML

@app.route("/api/status")
def api_status():
    players = []
    online_count = 0
    max_players = 20
    with _status_lock:
        players = list(status_cache["players"])
        online_count = len(players)
        props = get_props()
        max_players = int(props.get("max-players", 20))
    return ok({
        "online": status_cache["online"],
        "players": players,
        "online_count": online_count,
        "max_players": max_players,
        "mem_mb": status_cache["mem_mb"],
        "uptime": status_cache["uptime"],
        "started_at": status_cache["started_at"],
        "jar": str(find_jar() or ""),
        "server_dir": str(SERVER_DIR),
        "min_ram": MIN_RAM,
        "max_ram": MAX_RAM,
    })

@app.route("/api/ram", methods=["GET", "POST"])
def api_ram():
    global MIN_RAM, MAX_RAM
    if request.method == "GET":
        return ok({"min_ram": MIN_RAM, "max_ram": MAX_RAM})
    data = request.get_json(silent=True) or {}
    new_min = data.get("min_ram", "").strip().upper()
    new_max = data.get("max_ram", "").strip().upper()
    valid = re.compile(r"^\d+[MG]$")
    if not valid.match(new_min) or not valid.match(new_max):
        return fail("Invalid RAM format. Use e.g. 512M, 1G, 2G, 4G")
    if server_proc and server_proc.poll() is None:
        return fail("Stop the server before changing RAM.")
    MIN_RAM = new_min
    MAX_RAM = new_max
    save_config()
    return ok({"message": f"RAM set to {MIN_RAM} min / {MAX_RAM} max", "min_ram": MIN_RAM, "max_ram": MAX_RAM})

@app.route("/api/start", methods=["POST"])
def api_start():
    ok_, msg = start_minecraft()
    return ok({"message": msg}) if ok_ else fail(msg)

@app.route("/api/stop", methods=["POST"])
def api_stop():
    data = request.get_json(silent=True) or {}
    sec = int(data.get("seconds", 15))
    ok_, msg = stop_minecraft(sec)
    return ok({"message": msg}) if ok_ else fail(msg)

@app.route("/api/restart", methods=["POST"])
def api_restart():
    data = request.get_json(silent=True) or {}
    sec = int(data.get("seconds", 15))
    stop_minecraft(sec)
    time.sleep(2)
    ok_, msg = start_minecraft()
    return ok({"message": msg}) if ok_ else fail(msg)

@app.route("/api/command", methods=["POST"])
def api_command():
    data = request.get_json(silent=True) or {}
    cmd = data.get("command", "").strip()
    if not cmd:
        return fail("No command provided.")
    ok_, msg = send_minecraft(cmd)
    return ok({"message": msg}) if ok_ else fail(msg)

@app.route("/api/console")
def api_console():
    def stream():
        last_len = 0
        while True:
            # Send new lines since last check
            new_lines = console_history[last_len:]
            if new_lines:
                last_len = len(console_history)
                yield f"data: {json.dumps({'lines': new_lines})}\n\n"
            else:
                yield f"data: {json.dumps({'lines': []})}\n\n"
            time.sleep(0.5)
    return Response(stream(), mimetype="text/event-stream")

@app.route("/api/files")
def api_files():
    path_str = request.args.get("path", "")
    target = (SERVER_DIR / path_str).resolve()
    if not str(target).startswith(str(SERVER_DIR.resolve())):
        return fail("Access denied.")
    if target.is_dir():
        items = []
        for entry in sorted(target.iterdir()):
            items.append({
                "name": entry.name,
                "path": str(entry.relative_to(SERVER_DIR)),
                "is_dir": entry.is_dir(),
                "size": entry.stat().st_size if entry.is_file() else 0,
                "modified": datetime.fromtimestamp(entry.stat().st_mtime).isoformat(),
            })
        return ok({"items": items, "current": str(target.relative_to(SERVER_DIR))})
    elif target.is_file():
        try:
            content = target.read_text(encoding="utf-8", errors="replace")
            return ok({"content": content, "path": str(target.relative_to(SERVER_DIR)), "name": target.name})
        except Exception as e:
            return fail(str(e))
    return fail("Path not found.")

@app.route("/api/file/save", methods=["POST"])
def api_file_save():
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    content = data.get("content", "")
    target = (SERVER_DIR / path).resolve()
    if not str(target).startswith(str(SERVER_DIR.resolve())):
        return fail("Access denied.")
    try:
        target.write_text(content, encoding="utf-8")
        return ok({"message": "File saved."})
    except Exception as e:
        return fail(str(e))

@app.route("/api/backup", methods=["POST"])
def api_backup():
    worlds = [d for d in SERVER_DIR.iterdir() if d.is_dir() and ("world" in d.name.lower() or d.name.endswith("-world"))]
    if not worlds:
        return fail("No world directories found.")
    # Save before backup
    if server_proc and server_proc.poll() is None:
        try:
            server_proc.stdin.write("save-all\n")
            server_proc.stdin.flush()
        except:
            pass
        time.sleep(2)
    backup_dir = SERVER_DIR / "backups"
    backup_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    archive = backup_dir / f"world-backup-{ts}.tar.gz"
    with tarfile.open(str(archive), "w:gz") as tar:
        for d in worlds:
            tar.add(str(d), arcname=d.name)
    size = archive.stat().st_size
    return ok({"message": f"Backup created ({size//1024} KB)", "file": archive.name})

@app.route("/api/backups")
def api_backups():
    backup_dir = SERVER_DIR / "backups"
    if not backup_dir.exists():
        return ok({"backups": []})
    files = []
    for f in sorted(backup_dir.glob("world-backup-*.tar.gz"), reverse=True):
        files.append({
            "name": f.name,
            "size": f.stat().st_size // 1024,
            "date": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        })
    return ok({"backups": files})

@app.route("/api/backup/restore", methods=["POST"])
def api_backup_restore():
    data = request.get_json(silent=True) or {}
    name = data.get("file", "")
    archive = SERVER_DIR / "backups" / name
    if not archive.exists():
        return fail("Backup not found.")
    if server_proc and server_proc.poll() is None:
        return fail("Stop the server before restoring a backup.")
    with tarfile.open(str(archive), "r:gz") as tar:
        tar.extractall(path=str(SERVER_DIR))
    return ok({"message": f"Restored from {name}."})

# ── Properties API ────────────────────────────────────────────────────

@app.route("/api/properties", methods=["GET", "POST"])
def api_properties():
    if request.method == "GET":
        props = get_props()
        schema = PROPS_SCHEMA
        rich = {}
        for k, v in props.items():
            entry = dict(schema.get(k, {"type": "string", "cat": "other", "label": k, "desc": ""}))
            entry["key"] = k
            entry["value"] = v
            rich[k] = entry
        # Also include schema-only keys not yet in file
        for k, s in schema.items():
            if k not in rich:
                entry = dict(s)
                entry["key"] = k
                entry["value"] = s.get("default", "")
                rich[k] = entry
        return ok({"properties": list(rich.values())})
    data = request.get_json(silent=True) or {}
    changes = data.get("changes", {})
    if not changes:
        return fail("No changes provided.")
    if server_proc and server_proc.poll() is None:
        return fail("Stop the server for some property changes to take effect, or restart after saving.")
    ok_, msg = save_props(changes)
    return ok({"message": msg}) if ok_ else fail(msg)

# ── Modpacks / Resource Packs API ────────────────────────────────────

@app.route("/api/packs/search")
def api_packs_search():
    q = request.args.get("q", "")
    pt = request.args.get("type", "modpack")
    prov = request.args.get("provider", "modrinth")
    if not q:
        return fail("Search query required.")
    if prov == "modrinth":
        results = modrinth_search(q, pt)
        if isinstance(results, dict) and "error" in results:
            return fail(results["error"])
        return ok({"results": results, "provider": prov, "type": pt})
    return fail(f"Unknown provider: {prov}")

@app.route("/api/packs/versions")
def api_packs_versions():
    pid = request.args.get("id", "")
    if not pid:
        return fail("Project ID required.")
    versions = modrinth_versions(pid)
    if isinstance(versions, dict) and "error" in versions:
        return fail(versions["error"])
    return ok({"versions": versions})

@app.route("/api/packs/install", methods=["POST"])
def api_packs_install():
    data = request.get_json(silent=True) or {}
    file_url = data.get("file_url", "")
    filename = data.get("filename", "pack.zip")
    pack_type = data.get("type", "modpack")
    if not file_url:
        return fail("No file URL provided.")
    if pack_type == "resourcepack":
        dest_dir = SERVER_DIR / "resourcepacks"
    else:
        dest_dir = SERVER_DIR / "mods"
    dest = dest_dir / filename
    try:
        modrinth_download(file_url, dest)
    except Exception as e:
        return fail(f"Download failed: {e}")
    return ok({"message": f"Installed {filename}", "path": str(dest.relative_to(SERVER_DIR))})

@app.route("/api/packs/installed")
def api_packs_installed():
    return ok({"packs": list_installed_packs()})

@app.route("/api/packs/remove", methods=["POST"])
def api_packs_remove():
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    if not path:
        return fail("No path provided.")
    target = (SERVER_DIR / path).resolve()
    if not str(target).startswith(str(SERVER_DIR.resolve())):
        return fail("Access denied.")
    if not target.exists():
        return fail("File not found.")
    target.unlink()
    return ok({"message": f"Removed {target.name}"})

# ── HTML ──────────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Minecraft Web Console</title>
<style>
  *{margin:0;padding:0;box-sizing:border-box}
  body{font-family:'Segoe UI',system-ui,sans-serif;background:#0f0f0f;color:#e0e0e0;display:flex;height:100vh;overflow:hidden}
  ::-webkit-scrollbar{width:6px}
  ::-webkit-scrollbar-track{background:#1a1a1a}
  ::-webkit-scrollbar-thumb{background:#333;border-radius:3px}
  .sidebar{width:260px;background:#1a1a1a;border-right:1px solid #2a2a2a;display:flex;flex-direction:column;flex-shrink:0}
  .sidebar h2{padding:18px 16px;font-size:15px;font-weight:600;color:#aaa;text-transform:uppercase;letter-spacing:1px;border-bottom:1px solid #2a2a2a}
  .sidebar nav{flex:1;overflow-y:auto;padding:8px 0}
  .sidebar nav a{display:flex;align-items:center;gap:10px;padding:10px 18px;color:#bbb;text-decoration:none;font-size:14px;transition:.15s;border-left:3px solid transparent}
  .sidebar nav a:hover{background:#222;color:#fff}
  .sidebar nav a.active{background:#1e2a1e;color:#5ced73;border-left-color:#5ced73}
  .main{flex:1;display:flex;flex-direction:column;min-width:0}
  .topbar{display:flex;align-items:center;gap:12px;padding:12px 24px;background:#1a1a1a;border-bottom:1px solid #2a2a2a;flex-shrink:0}
  .topbar .dot{width:10px;height:10px;border-radius:50%;display:inline-block}
  .dot.green{background:#5ced73;box-shadow:0 0 6px #5ced7380}
  .dot.red{background:#ff4444;box-shadow:0 0 6px #ff444480}
  .topbar .stat{padding:4px 12px;border-radius:4px;font-size:13px}
  .topbar .stat.mem{background:#1e3a2e;color:#5ced73}
  .topbar .stat.players{background:#2a1e3a;color:#b388ff}
  .topbar .stat.uptime{background:#1e2a3a;color:#64b5f6}
  .content{flex:1;overflow-y:auto;padding:24px}
  .page{display:none}
  .page.active{display:block}
  .server-actions{display:flex;gap:10px;margin-bottom:24px;flex-wrap:wrap}
  .btn{padding:10px 22px;border:none;border-radius:6px;font-size:14px;font-weight:600;cursor:pointer;transition:.15s;display:inline-flex;align-items:center;gap:6px}
  .btn:disabled{opacity:.4;cursor:not-allowed}
  .btn-start{background:#2e7d32;color:#fff}.btn-start:hover{background:#388e3c}
  .btn-stop{background:#c62828;color:#fff}.btn-stop:hover{background:#d32f2f}
  .btn-restart{background:#e65100;color:#fff}.btn-restart:hover{background:#ef6c00}
  .btn-cmd{background:#1565c0;color:#fff}.btn-cmd:hover{background:#1976d2}
  .btn-backup{background:#4a148c;color:#fff}.btn-backup:hover{background:#6a1b9a}
  .btn-save{background:#00695c;color:#fff}.btn-save:hover{background:#00796b}
  .btn-secondary{background:#333;color:#ccc}.btn-secondary:hover{background:#444;color:#fff}
  .btn-danger{background:#7f0000;color:#fff}.btn-danger:hover{background:#b71c1c}
  .console-wrap{background:#0a0a0a;border:1px solid #2a2a2a;border-radius:8px;overflow:hidden}
  .console-header{display:flex;justify-content:space-between;align-items:center;padding:8px 16px;background:#111;border-bottom:1px solid #2a2a2a;font-size:12px;color:#888}
  .console{height:400px;overflow-y:auto;padding:12px 16px;font-family:'JetBrains Mono','Cascadia Code','Fira Code',monospace;font-size:13px;line-height:1.5;white-space:pre-wrap;word-break:break-all;color:#ccc}
  .console .ts{color:#666;margin-right:8px}
  .console .info{color:#4fc3f7}
  .console .warn{color:#ffd54f}
  .console .err,.console .error{color:#ef5350}
  .console .done{color:#69f0ae}
  .console .say{color:#ce93d8}
  .cmd-bar{display:flex;gap:8px;padding:10px 16px;background:#111;border-top:1px solid #2a2a2a}
  .cmd-bar input{flex:1;padding:8px 12px;background:#1a1a1a;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-family:monospace;font-size:13px;outline:none}
  .cmd-bar input:focus{border-color:#5ced73}
  .file-browser{display:flex;gap:1px;height:calc(100vh - 180px);min-height:400px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;overflow:hidden}
  .file-tree{width:220px;overflow-y:auto;background:#111;padding:8px 0;flex-shrink:0}
  .file-tree .fi{padding:6px 14px;font-size:13px;cursor:pointer;color:#aaa;transition:.1s;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .file-tree .fi:hover{background:#222;color:#fff}
  .file-tree .fi.folder{color:#fdd835}
  .file-tree .fi.file{color:#90caf9}
  .file-tree .fi.active{background:#1e2a1e;color:#5ced73}
  .file-editor{flex:1;display:flex;flex-direction:column}
  .file-editor .fe-header{padding:8px 16px;background:#151515;border-bottom:1px solid #2a2a2a;font-size:13px;color:#888;display:flex;justify-content:space-between;align-items:center}
  .file-editor textarea{flex:1;background:#0d0d0d;border:none;color:#e0e0e0;font-family:monospace;font-size:13px;padding:12px 16px;resize:none;outline:none;tab-size:2}
  .file-editor .fe-actions{padding:8px 16px;background:#151515;border-top:1px solid #2a2a2a;display:flex;gap:8px}
  .backups-list{display:grid;gap:8px}
  .backup-item{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px}
  .backup-item .bi-info{font-size:13px}
  .backup-item .bi-info strong{color:#ccc}
  .backup-item .bi-info span{color:#888;margin-left:8px}
  .toast{position:fixed;bottom:24px;right:24px;padding:12px 20px;border-radius:6px;font-size:14px;z-index:100;opacity:0;transition:opacity .3s}
  .toast.show{opacity:1}
  .toast.success{background:#2e7d32;color:#fff}
  .toast.error{background:#b71c1c;color:#fff}
  .toast.info{background:#1565c0;color:#fff}
  .loading{text-align:center;padding:40px;color:#666}
  .status-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin-bottom:24px}
  .stat-card{padding:16px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;text-align:center}
  .stat-card .sc-val{font-size:24px;font-weight:700;margin-top:4px}
  .stat-card .sc-label{font-size:12px;color:#888;text-transform:uppercase;letter-spacing:1px}
  .modal{display:none;position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:50;align-items:center;justify-content:center}
  .modal.show{display:flex}
  .modal-box{background:#1a1a1a;border:1px solid #333;border-radius:8px;padding:24px;min-width:320px}
  .modal-box h3{margin-bottom:16px}
  .modal-box input{width:100%;padding:8px 12px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;margin-bottom:12px;outline:none}
  .modal-box input:focus{border-color:#5ced73}
  .modal-actions{display:flex;gap:8px;justify-content:flex-end}
  .props-cat{margin-bottom:20px}
  .props-cat h4{font-size:13px;color:#888;text-transform:uppercase;letter-spacing:1px;margin-bottom:10px;padding-bottom:6px;border-bottom:1px solid #2a2a2a}
  .prop-row{display:flex;align-items:center;justify-content:space-between;padding:8px 12px;background:#151515;border:1px solid #2a2a2a;border-radius:4px;margin-bottom:6px}
  .prop-row .pr-label{font-size:13px}
  .prop-row .pr-label small{display:block;font-size:11px;color:#666;margin-top:2px}
  .toggle{position:relative;width:44px;height:24px;flex-shrink:0}
  .toggle input{opacity:0;width:0;height:0}
  .toggle .slider{position:absolute;cursor:pointer;inset:0;background:#333;border-radius:12px;transition:.2s}
  .toggle .slider::before{content:"";position:absolute;width:18px;height:18px;border-radius:50%;background:#888;top:3px;left:3px;transition:.2s}
  .toggle input:checked+.slider{background:#2e7d32}
  .toggle input:checked+.slider::before{background:#fff;transform:translateX(20px)}
  .prop-row select,.prop-row input[type=number],.prop-row input[type=text]{padding:6px 10px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-size:13px;outline:none;width:160px}
  .prop-row select:focus,.prop-row input:focus{border-color:#5ced73}
  .props-save-bar{position:sticky;bottom:0;padding:12px 0;text-align:right}
  .pack-search-bar{display:flex;gap:8px;margin-bottom:16px;flex-wrap:wrap}
  .pack-search-bar input{flex:1;min-width:200px;padding:10px 14px;background:#111;border:1px solid #333;border-radius:6px;color:#e0e0e0;font-size:14px;outline:none}
  .pack-search-bar input:focus{border-color:#5ced73}
  .pack-search-bar select{padding:10px 14px;background:#111;border:1px solid #333;border-radius:6px;color:#e0e0e0;font-size:14px;outline:none}
  .pack-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
  .pack-card{background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px;padding:14px;display:flex;gap:12px;transition:.15s}
  .pack-card:hover{border-color:#444}
  .pack-card img{width:48px;height:48px;border-radius:6px;flex-shrink:0;object-fit:cover;background:#111}
  .pack-card .pc-body{flex:1;min-width:0}
  .pack-card .pc-body h4{font-size:14px;margin-bottom:4px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .pack-card .pc-body p{font-size:12px;color:#888;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
  .pack-card .pc-body .pc-meta{font-size:11px;color:#666;margin-top:6px}
  .pack-card .pc-body .pc-meta span{margin-right:10px}
  .pack-subnav{display:flex;gap:8px;margin-bottom:16px}
  .pack-subnav button{padding:8px 18px;border:1px solid #333;border-radius:6px;background:#1a1a1a;color:#aaa;font-size:13px;cursor:pointer}
  .pack-subnav button.active{background:#2e7d32;color:#fff;border-color:#2e7d32}
  .installed-list{display:grid;gap:8px}
  .installed-item{display:flex;justify-content:space-between;align-items:center;padding:10px 14px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:6px}
  .installed-item .ii-info{font-size:13px}
  .installed-item .ii-info strong{color:#ccc}
  .installed-item .ii-info span{color:#888;margin-left:8px}
  .search-status{padding:12px;text-align:center;color:#666;font-size:13px}
  @media(max-width:768px){.sidebar{display:none}.content{padding:12px}}
</style>
</head>
<body>
<div class="sidebar">
  <h2>Minecraft Console</h2>
  <nav>
    <a href="#" class="active" data-page="dashboard">Dashboard</a>
    <a href="#" data-page="console">Console</a>
    <a href="#" data-page="properties">Settings</a>
    <a href="#" data-page="packs">Modpacks</a>
    <a href="#" data-page="files">File Manager</a>
    <a href="#" data-page="backups">Backups</a>
  </nav>
</div>
<div class="main">
  <div class="topbar">
    <span class="dot" id="statusDot"></span>
    <span id="statusLabel" style="font-weight:600;font-size:14px">Loading...</span>
    <span class="stat mem" id="memStat">— MB</span>
    <span class="stat players" id="playerStat">0 online</span>
    <span class="stat uptime" id="uptimeStat">—</span>
  </div>
  <div class="content" id="mainContent">
    <div class="page active" id="page-dashboard"></div>
    <div class="page" id="page-console">
      <div class="server-actions">
        <button class="btn btn-start" onclick="api('start')">Start</button>
        <button class="btn btn-stop" onclick="showStopModal()">Stop</button>
        <button class="btn btn-restart" onclick="showRestartModal()">Restart</button>
      </div>
      <div class="console-wrap">
        <div class="console-header"><span>Server Console</span><button class="btn btn-secondary" style="padding:4px 10px;font-size:12px" onclick="clearConsole()">Clear</button></div>
        <div class="console" id="consoleOutput"><span style="color:#555">Server not running — start it to see console output</span></div>
        <form class="cmd-bar" onsubmit="return sendCmd(event)">
          <input type="text" id="cmdInput" placeholder="Type a command..." autocomplete="off">
          <button class="btn btn-cmd" type="submit">Send</button>
        </form>
      </div>
    </div>
    <div class="page" id="page-files"><div id="fileBrowser" class="loading">Loading files...</div></div>
    <div class="page" id="page-properties"></div>
    <div class="page" id="page-packs">
      <div class="pack-subnav">
        <button class="active" id="packBrowseBtn" onclick="showPackTab('browse')">Browse</button>
        <button id="packInstalledBtn" onclick="showPackTab('installed')">Installed</button>
      </div>
      <div id="packBrowse">
        <div class="pack-search-bar">
          <input type="text" id="packSearchInput" placeholder="Search modpacks..." onkeydown="if(event.key==='Enter')searchPacks()">
          <select id="packTypeSelect"><option value="modpack">Modpacks</option><option value="resourcepack">Resource Packs</option></select>
          <button class="btn btn-cmd" onclick="searchPacks()">Search</button>
        </div>
        <div id="packResults"></div>
      </div>
      <div id="packInstalled" style="display:none"><div id="packInstalledList"></div></div>
    </div>
    <div class="page" id="page-backups">
      <div class="server-actions">
        <button class="btn btn-backup" onclick="createBackup()">Create Backup</button>
      </div>
      <div id="backupsList"></div>
    </div>
  </div>
</div>

<div class="modal" id="stopModal">
  <div class="modal-box">
    <h3>Stop Server</h3>
    <label style="font-size:13px;color:#888">Warning time (seconds):</label>
    <input type="number" id="stopSeconds" value="15" min="0" max="120">
    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeModal('stopModal')">Cancel</button>
      <button class="btn btn-stop" onclick="doStop()">Stop</button>
    </div>
  </div>
</div>
<div class="modal" id="restartModal">
  <div class="modal-box">
    <h3>Restart Server</h3>
    <label style="font-size:13px;color:#888">Warning time (seconds):</label>
    <input type="number" id="restartSeconds" value="15" min="0" max="120">
    <div class="modal-actions">
      <button class="btn btn-secondary" onclick="closeModal('restartModal')">Cancel</button>
      <button class="btn btn-restart" onclick="doRestart()">Restart</button>
    </div>
  </div>
</div>
<div class="modal" id="versionModal">
  <div class="modal-box">
    <h3 id="versionModalTitle">Select Version</h3>
    <div id="versionList"></div>
    <div class="modal-actions" style="margin-top:12px">
      <button class="btn btn-secondary" onclick="closeModal('versionModal')">Cancel</button>
    </div>
  </div>
</div>
<div class="toast" id="toast"></div>

<script>
let statusPoll = null;
let consoleStream = null;
let currentFile = null;
let currentFilePath = null;

function $(id){return document.getElementById(id)}

// ── Navigation ──
document.querySelectorAll('.sidebar nav a').forEach(a => {
  a.onclick = e => {
    e.preventDefault();
    document.querySelectorAll('.sidebar nav a').forEach(x => x.classList.remove('active'));
    a.classList.add('active');
    showPage(a.dataset.page);
  };
});

function showPage(name) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  $(`page-${name}`).classList.add('active');
  if (name === 'console') setupConsole();
  if (name === 'files') loadFileTree();
  if (name === 'backups') loadBackups();
  if (name === 'dashboard') loadDashboard();
  if (name === 'properties') loadProperties();
  if (name === 'packs') { loadInstalledPacks(); }
}

// ── Toast ──
function toast(msg, type='info') {
  const t = $('toast');
  t.textContent = msg;
  t.className = `toast ${type} show`;
  setTimeout(() => t.classList.remove('show'), 3000);
}

// ── Fetch helpers ──
async function api(method, body) {
  const opts = {method:'POST'};
  if (body) opts.body = JSON.stringify(body), opts.headers = {'Content-Type':'application/json'};
  const r = await fetch(`/api/${method}`, opts);
  const d = await r.json();
  if (!d.ok) toast(d.error, 'error');
  else if (d.message) toast(d.message, 'success');
  return d;
}

async function get(path) {
  const r = await fetch(path);
  return r.json();
}

// ── Status bar ──
function updateStatus(data) {
  const dot = $('statusDot');
  const label = $('statusLabel');
  if (data.online) {
    dot.className = 'dot green';
    label.textContent = 'Running';
    label.style.color = '#5ced73';
  } else {
    dot.className = 'dot red';
    label.textContent = 'Stopped';
    label.style.color = '#ff4444';
  }
  $('memStat').textContent = data.mem_mb ? `${data.mem_mb} MB` : '— MB';
  $('playerStat').textContent = `${data.online_count}/${data.max_players} online`;
  $('uptimeStat').textContent = data.uptime || '—';
}

async function pollStatus() {
  const d = await get('/api/status');
  updateStatus(d);
}

setInterval(pollStatus, 3000);
pollStatus();

// ── Dashboard ──
async function loadDashboard() {
  const d = await get('/api/status');
  const pg = $('page-dashboard');
  pg.innerHTML = `
    <div class="status-grid">
      <div class="stat-card"><div class="sc-label">Status</div><div class="sc-val" style="color:${d.online?'#5ced73':'#ff4444'}">${d.online?'Running':'Stopped'}</div></div>
      <div class="stat-card"><div class="sc-label">Players</div><div class="sc-val" style="color:#b388ff">${d.online_count} / ${d.max_players}</div></div>
      <div class="stat-card"><div class="sc-label">Memory</div><div class="sc-val" style="color:#5ced73">${d.mem_mb||'—'} MB</div></div>
      <div class="stat-card"><div class="sc-label">Uptime</div><div class="sc-val" style="color:#64b5f6;font-size:18px">${d.uptime||'—'}</div></div>
    </div>
    <div class="server-actions">
      <button class="btn btn-start" onclick="api('start')">Start Server</button>
      <button class="btn btn-stop" onclick="showStopModal()">Stop Server</button>
      <button class="btn btn-restart" onclick="showRestartModal()">Restart Server</button>
    </div>
    <div style="margin-top:20px;padding:16px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px">
      <h3 style="margin-bottom:8px;font-size:14px;color:#888;text-transform:uppercase">Server Info</h3>
      <table style="width:100%;font-size:13px;border-collapse:collapse">
        <tr><td style="padding:6px 0;color:#888">Jar</td><td style="padding:6px 0">${d.jar||'—'}</td></tr>
        <tr><td style="padding:6px 0;color:#888">Directory</td><td style="padding:6px 0">${d.server_dir}</td></tr>
        <tr><td style="padding:6px 0;color:#888">Players</td><td style="padding:6px 0">${d.players.length ? d.players.join(', ') : 'None'}</td></tr>
      </table>
    </div>
    <div style="margin-top:16px;padding:16px;background:#1a1a1a;border:1px solid #2a2a2a;border-radius:8px">
      <h3 style="margin-bottom:8px;font-size:14px;color:#888;text-transform:uppercase">RAM Allocation</h3>
      <div style="display:flex;gap:12px;align-items:end;flex-wrap:wrap">
        <div>
          <label style="font-size:12px;color:#888">Min RAM</label>
          <input type="text" id="ramMin" value="${d.min_ram}" style="width:90px;padding:8px 10px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-size:14px;outline:none;margin-top:4px">
        </div>
        <div>
          <label style="font-size:12px;color:#888">Max RAM</label>
          <input type="text" id="ramMax" value="${d.max_ram}" style="width:90px;padding:8px 10px;background:#111;border:1px solid #333;border-radius:4px;color:#e0e0e0;font-size:14px;outline:none;margin-top:4px">
        </div>
        <button class="btn btn-save" style="padding:8px 18px" onclick="saveRam()" id="ramSaveBtn">Save RAM</button>
      </div>
      <div style="font-size:12px;color:#666;margin-top:8px">Examples: 512M, 1G, 2G, 4G — stop server before changing</div>
    </div>
  `;
}

async function saveRam() {
  const min = $('ramMin').value.trim().toUpperCase();
  const max = $('ramMax').value.trim().toUpperCase();
  const btn = $('ramSaveBtn');
  btn.textContent = 'Saving...';
  btn.disabled = true;
  const d = await api('ram', {min_ram: min, max_ram: max});
  btn.textContent = 'Save RAM';
  btn.disabled = false;
}

// ── Properties / Settings ──
async function loadProperties() {
  const d = await get('/api/properties');
  if (!d.ok) { $('page-properties').innerHTML = `<div class="search-status">${d.error}</div>`; return; }
  const props = d.properties || [];
  const cats = {};
  for (const p of props) {
    const cat = p.cat || 'other';
    if (!cats[cat]) cats[cat] = [];
    cats[cat].push(p);
  }
  const catOrder = ['server', 'gameplay', 'world', 'network', 'other'];
  let html = '';
  for (const c of catOrder) {
    if (!cats[c]) continue;
    html += `<div class="props-cat"><h4>${c.charAt(0).toUpperCase() + c.slice(1)}</h4>`;
    for (const p of cats[c]) {
      html += `<div class="prop-row" data-key="${p.key}"><div class="pr-label">${escapeHtml(p.label)}<small>${escapeHtml(p.desc)}</small></div>`;
      const val = p.value;
      if (p.type === 'bool') {
        const checked = val === 'true' ? 'checked' : '';
        html += `<label class="toggle"><input type="checkbox" ${checked} onchange="propChanged('${p.key}',this.checked?'true':'false')"><span class="slider"></span></label>`;
      } else if (p.type === 'enum') {
        html += `<select onchange="propChanged('${p.key}',this.value)">`;
        for (const o of (p.opts || [])) {
          html += `<option value="${o}" ${o===val?'selected':''}>${o}</option>`;
        }
        html += `</select>`;
      } else if (p.type === 'number') {
        html += `<input type="number" value="${escapeHtml(val)}" ${p.min!==undefined?`min="${p.min}"`:''} ${p.max!==undefined?`max="${p.max}"`:''} onchange="propChanged('${p.key}',this.value)">`;
      } else {
        html += `<input type="text" value="${escapeHtml(val)}" onchange="propChanged('${p.key}',this.value)">`;
      }
      html += '</div>';
    }
    html += '</div>';
  }
  html += `<div class="props-save-bar"><button class="btn btn-save" onclick="saveProperties()" id="propsSaveBtn">Save Properties</button></div>`;
  $('page-properties').innerHTML = html;
  window._propChanges = {};
}

function propChanged(key, value) {
  if (!window._propChanges) window._propChanges = {};
  window._propChanges[key] = value;
}

async function saveProperties() {
  const changes = window._propChanges || {};
  if (!Object.keys(changes).length) { toast('No changes to save', 'info'); return; }
  const btn = $('propsSaveBtn');
  btn.textContent = 'Saving...';
  btn.disabled = true;
  const d = await api('properties', {changes});
  btn.textContent = 'Save Properties';
  btn.disabled = false;
  if (d.ok) {
    window._propChanges = {};
    toast('Properties saved — restart server to apply', 'success');
  }
}

// ── Modpacks / Resource Packs ──
function showPackTab(tab) {
  $('packBrowse').style.display = tab === 'browse' ? 'block' : 'none';
  $('packInstalled').style.display = tab === 'installed' ? 'block' : 'none';
  $('packBrowseBtn').className = tab === 'browse' ? 'active' : '';
  $('packInstalledBtn').className = tab === 'installed' ? 'active' : '';
  if (tab === 'installed') loadInstalledPacks();
}

let _packSearchTimeout = null;

async function searchPacks() {
  const q = $('packSearchInput').value.trim();
  const type = $('packTypeSelect').value;
  if (!q) { toast('Enter a search term', 'info'); return; }
  const container = $('packResults');
  container.innerHTML = '<div class="search-status">Searching...</div>';
  const d = await get(`/api/packs/search?q=${encodeURIComponent(q)}&type=${type}`);
  if (!d.ok || !d.results) { container.innerHTML = `<div class="search-status">${d.error||'No results'}</div>`; return; }
  if (!d.results.length) { container.innerHTML = '<div class="search-status">No results found</div>'; return; }
  let html = '<div class="pack-grid">';
  for (const r of d.results) {
    const icon = r.icon_url || '';
    const dl = r.downloads >= 1000 ? Math.floor(r.downloads/1000)+'k' : r.downloads;
    html += `<div class="pack-card">
      <img src="${icon}" alt="" onerror="this.src='data:image/svg+xml,<svg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 48 48%22><rect fill=%22%23333%22 width=%2248%22 height=%2248%22/><text x=%2224%22 y=%2232%22 text-anchor=%22middle%22 fill=%22%23888%22 font-size=%2224%22>?</text></svg>'">
      <div class="pc-body">
        <h4>${escapeHtml(r.title)}</h4>
        <p>${escapeHtml(r.description)}</p>
        <div class="pc-meta">
          <span>${escapeHtml(r.author)}</span>
          <span>${dl} downloads</span>
          <span>${r.latest_version||''}</span>
        </div>
        <button class="btn btn-cmd" style="padding:4px 12px;font-size:12px;margin-top:6px" onclick="showVersions('${r.id}','${escapeHtml(r.title)}','${type}')">Install</button>
      </div>
    </div>`;
  }
  html += '</div>';
  container.innerHTML = html;
}

async function showVersions(projectId, title, packType) {
  $('versionModalTitle').textContent = `Versions — ${title}`;
  $('versionList').innerHTML = '<div class="search-status">Loading...</div>';
  $('versionModal').classList.add('show');
  const d = await get(`/api/packs/versions?id=${projectId}`);
  if (!d.ok || !d.versions) { $('versionList').innerHTML = `<div class="search-status">${d.error||'Failed to load'}</div>`; return; }
  if (!d.versions.length) { $('versionList').innerHTML = '<div class="search-status">No versions found</div>'; return; }
  let html = '<div style="max-height:300px;overflow-y:auto">';
  for (const v of d.versions) {
    const gameVer = (v.game_versions||[]).slice(0,3).join(', ') + ((v.game_versions||[]).length > 3 ? '...' : '');
    const loaders = (v.loaders||[]).join(', ');
    for (const f of (v.files||[]).slice(0,1)) {
      const size = f.size >= 1048576 ? (f.size/1048576).toFixed(1)+' MB' : (f.size/1024).toFixed(0)+' KB';
      html += `<div style="padding:10px;border:1px solid #2a2a2a;border-radius:4px;margin-bottom:6px;background:#151515">
        <div style="font-size:13px"><strong>${escapeHtml(v.name)}</strong> <span style="color:#888">${v.version_number}</span></div>
        <div style="font-size:12px;color:#666;margin:4px 0">${gameVer} | ${loaders} | ${size}</div>
        <button class="btn btn-start" style="padding:4px 12px;font-size:12px" onclick="installPack('${f.url}','${f.filename}','${packType}')">Download</button>
      </div>`;
    }
  }
  html += '</div>';
  $('versionList').innerHTML = html;
}

async function installPack(fileUrl, filename, packType) {
  closeModal('versionModal');
  toast('Installing...', 'info');
  const d = await api('packs/install', {file_url: fileUrl, filename, type: packType});
  if (d.ok) {
    toast(`Installed ${filename}`, 'success');
    loadInstalledPacks();
  }
}

async function loadInstalledPacks() {
  const d = await get('/api/packs/installed');
  const container = $('packInstalledList');
  if (!d.ok || !d.packs || !d.packs.length) {
    container.innerHTML = '<div class="search-status">Nothing installed yet</div>';
    return;
  }
  let html = '<div class="installed-list">';
  for (const p of d.packs) {
    const size = p.size >= 1048576 ? (p.size/1048576).toFixed(1)+' MB' : (p.size/1024).toFixed(0)+' KB';
    const label = p.type === 'mod' ? 'Mod' : 'Resource Pack';
    html += `<div class="installed-item">
      <div class="ii-info"><strong>${escapeHtml(p.name)}</strong><span>${label}</span><span>${size}</span></div>
      <button class="btn btn-danger" style="padding:4px 12px;font-size:12px" onclick="removePack('${p.path}','${escapeHtml(p.name)}')">Remove</button>
    </div>`;
  }
  html += '</div>';
  container.innerHTML = html;
}

async function removePack(path, name) {
  if (!confirm(`Remove ${name}?`)) return;
  const d = await api('packs/remove', {path});
  if (d.ok) { toast(`Removed ${name}`, 'success'); loadInstalledPacks(); }
}

// ── Console ──
function setupConsole() {
  if (consoleStream) return;
  const out = $('consoleOutput');
  const es = new EventSource('/api/console');
  consoleStream = es;
  let lineCount = 0;
  es.onmessage = e => {
    const d = JSON.parse(e.data);
    if (!d.lines || !d.lines.length) return;
    // Only append new lines (after the first batch)
    if (lineCount > 0 && d.lines.length <= lineCount) return;
    const newLines = lineCount === 0 ? d.lines : d.lines.slice(lineCount);
    lineCount = d.lines.length;
    // Clear placeholder on first real output
    if (d.lines.length > 0 && out.children.length === 1 && out.children[0].textContent.includes('not running')) {
      out.innerHTML = '';
    }
    for (const line of newLines) {
      const div = document.createElement('div');
      let cls = '';
      let text = line;
      // Strip Minecraft color codes
      text = text.replace(/\xa7[0-9a-fklmnor]/g, '');
      text = text.replace(/\u00a7[0-9a-fklmnor]/g, '');
      // Color by log level
      if (/\[.*\/INFO\]:/.test(line) || /]: <|]: \[Not Secure\]/.test(line)) cls = 'info';
      if (/\[.*\/WARN\]:/.test(line)) cls = 'warn';
      if (/\[.*\/ERROR\]:/.test(line)) cls = 'error';
      if (/joined the game/.test(line)) cls = 'done';
      if (/left the game/.test(line)) cls = 'warn';
      if (/\[.*\/FATAL\]:/.test(line)) cls = 'error';
      if (/^\[[0-9]{2}:[0-9]{2}:[0-9]{2}\] \[Server thread\/INFO\]: Done /.test(line)) cls = 'done';
      if (/]: .* whispers: /.test(line)) cls = 'say';
      if (/]: .* </.test(line) && !/]: \[Not Secure\]/.test(line)) cls = 'say';
      // Timestamp from log line
      let ts = '';
      const tm = line.match(/^\[([0-9]{2}:[0-9]{2}:[0-9]{2})\]/);
      if (tm) ts = tm[1];
      div.innerHTML = `<span class="ts">${ts}</span><span class="${cls}">${escapeHtml(text)}</span>`;
      out.appendChild(div);
    }
    out.scrollTop = out.scrollHeight;
  };
}

function clearConsole() {
  $('consoleOutput').innerHTML = '<span style="color:#555">Server not running — start it to see console output</span>';
}

function sendCmd(e) {
  e.preventDefault();
  const input = $('cmdInput');
  const cmd = input.value.trim();
  if (!cmd) return;
  api('command', {command: cmd});
  input.value = '';
}

// ── Modals ──
function showStopModal() { $('stopModal').classList.add('show') }
function showRestartModal() { $('restartModal').classList.add('show') }
function closeModal(id) { $(id).classList.remove('show') }
function doStop() { closeModal('stopModal'); api('stop', {seconds: parseInt($('stopSeconds').value) || 15}) }
function doRestart() { closeModal('restartModal'); api('restart', {seconds: parseInt($('restartSeconds').value) || 15}) }

// ── File Manager ──
async function loadFileTree(path) {
  const d = await get(`/api/files?path=${path||''}`);
  if (!d.ok) { $('fileBrowser').innerHTML = `<div class="loading">${d.error}</div>`; return }
  const items = d.items || [];
  const html = ['<div class="file-browser"><div class="file-tree">'];
  if (d.current) html.push(`<div class="fi folder" onclick="loadFileTree('')">.. (root)</div>`);
  for (const item of items) {
    const icon = item.is_dir ? '' : '';
    const cls = item.is_dir ? 'folder' : 'file';
    const click = item.is_dir ? `loadFileTree('${item.path}')` : `openFile('${item.path}')`;
    html.push(`<div class="fi ${cls}" onclick="${click}">${icon} ${item.name}</div>`);
  }
  html.push('</div><div class="file-editor" id="fileEditor"><div class="fe-header">Select a file to edit</div></div></div>');
  $('fileBrowser').innerHTML = html.join('');
}

async function openFile(path) {
  const d = await get(`/api/files?path=${path}`);
  if (!d.ok) { toast(d.error, 'error'); return }
  currentFilePath = path;
  currentFile = d.name;
  const eds = document.getElementById('fileEditor');
  if (!eds) return;
  const isProps = d.name === 'server.properties' || d.name === 'eula.txt';
  eds.innerHTML = `
    <div class="fe-header"><span>${escapeHtml(d.path)}</span><span style="color:#666">${isProps ? 'Editing this will restart the server to take effect.' : ''}</span></div>
    <textarea id="fileContent" spellcheck="false">${escapeHtml(d.content)}</textarea>
    <div class="fe-actions">
      <button class="btn btn-save" onclick="saveFile()">Save</button>
      <button class="btn btn-secondary" onclick="loadFileTree()">Cancel</button>
    </div>
  `;
}

async function saveFile() {
  const content = document.getElementById('fileContent').value;
  if (!currentFilePath) return;
  const d = await api('file/save', {path: currentFilePath, content});
  if (d.ok) toast('File saved!', 'success');
}

// ── Backups ──
async function loadBackups() {
  const d = await get('/api/backups');
  const list = $('backupsList');
  if (!d.backups || !d.backups.length) {
    list.innerHTML = '<div style="padding:24px;text-align:center;color:#666">No backups yet.</div>';
    return;
  }
  let html = '<div class="backups-list">';
  for (const b of d.backups) {
    html += `<div class="backup-item">
      <div class="bi-info"><strong>${escapeHtml(b.name)}</strong><span>${b.size} KB</span><span>${b.date}</span></div>
      <div><button class="btn btn-secondary" style="padding:4px 12px;font-size:12px" onclick="restoreBackup('${b.name}')">Restore</button></div>
    </div>`;
  }
  html += '</div>';
  list.innerHTML = html;
}

async function createBackup() {
  const d = await api('backup');
  if (d.ok) { loadBackups(); toast('Backup created!', 'success'); }
}

async function restoreBackup(name) {
  if (!confirm('Restore this backup? The server will be overwritten.')) return;
  const d = await api('backup/restore', {file: name});
  if (d.ok) toast('Backup restored!', 'success');
}

// ── Utility ──
function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// Init
loadDashboard();
</script>
</body>
</html>
"""

# ── CLI ───────────────────────────────────────────────────────────────

def main():
    global SERVER_DIR, PORT, HOST
    ap = argparse.ArgumentParser(description="Minecraft Web Manager for Termux")
    ap.add_argument("--dir", help=f"Server directory (default: {SERVER_DIR})")
    ap.add_argument("--port", type=int, help=f"Web port (default: {PORT})")
    ap.add_argument("--host", help=f"Bind address (default: {HOST})")
    args = ap.parse_args()
    if args.dir:
        SERVER_DIR = Path(args.dir).resolve()
    if args.port:
        PORT = args.port
    if args.host:
        HOST = args.host

    if not SERVER_DIR.exists():
        print(f"[!] Server directory does not exist: {SERVER_DIR}")
        sys.exit(1)

    load_config()

    print(f" Minecraft Web Manager")
    print(f"  Server directory: {SERVER_DIR}")
    print(f"  Web URL:          http://localhost:{PORT}")
    print(f"  Start server:     Open browser and click Start")
    print()

    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)

if __name__ == "__main__":
    main()

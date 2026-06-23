"""Multi-server instance management.

Each Minecraft server is a ServerInstance with its own:
  - directory, process, console history/queue
  - status cache, RAM config, port, jar type
  - reader thread, poll thread

The registry persists to ~/mc-servers.json and scans ~/mc-servers/ for dirs.
"""

import json
import os
import queue
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

SERVERS_BASE = Path.home() / "mc-servers"
REGISTRY_PATH = Path.home() / "mc-servers.json"
CONSOLE_MAX = 500


class ServerInstance:
    def __init__(self, sid, name, server_dir, jar_type="vanilla",
                 min_ram="512M", max_ram="2G", port=25565):
        self.id = sid
        self.name = name
        self.dir = Path(server_dir)
        self.jar_type = jar_type
        self.min_ram = min_ram
        self.max_ram = max_ram
        self.port = port

        self.proc = None
        self.console_history = []
        self.console_queue = queue.Queue()
        self.status_cache = {
            "online": False, "players": [], "tps": 0,
            "uptime": "", "mem_mb": 0, "started_at": "",
        }
        self._lock = threading.Lock()
        self._reader_thread = None
        self._poll_thread = None

    @property
    def lock(self):
        return self._lock

    def is_running(self):
        return self.proc is not None and self.proc.poll() is None

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "dir": str(self.dir),
            "jar_type": self.jar_type,
            "min_ram": self.min_ram,
            "max_ram": self.max_ram,
            "port": self.port,
            "online": self.is_running(),
        }

    def status_dict(self):
        with self._lock:
            players = list(self.status_cache["players"])
        jar = ""
        for f in sorted(self.dir.glob("*.jar")):
            jar = f.name
            break
        return {
            "id": self.id,
            "name": self.name,
            "online": self.is_running(),
            "players": players,
            "online_count": len(players),
            "max_players": 20,
            "mem_mb": self.status_cache["mem_mb"],
            "uptime": self.status_cache["uptime"],
            "started_at": self.status_cache["started_at"],
            "jar": jar,
            "server_dir": str(self.dir),
            "min_ram": self.min_ram,
            "max_ram": self.max_ram,
            "port": self.port,
            "jar_type": self.jar_type,
        }

    def save_config(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        cfg = self.dir / ".webconsole.json"
        existing = {}
        if cfg.exists():
            try:
                existing = json.loads(cfg.read_text())
            except Exception:
                pass
        existing["min_ram"] = self.min_ram
        existing["max_ram"] = self.max_ram
        existing["jar_type"] = self.jar_type
        existing["port"] = self.port
        cfg.write_text(json.dumps(existing, indent=2))

    def load_config(self):
        cfg = self.dir / ".webconsole.json"
        if cfg.exists():
            try:
                data = json.loads(cfg.read_text())
                self.min_ram = data.get("min_ram", self.min_ram)
                self.max_ram = data.get("max_ram", self.max_ram)
                self.jar_type = data.get("jar_type", self.jar_type)
                self.port = data.get("port", self.port)
            except Exception:
                pass


_servers = {}
_registry_lock = threading.Lock()


def get_server(sid):
    return _servers.get(sid)


def all_servers():
    return list(_servers.values())


def _gen_id(name):
    import re
    base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')
    if not base:
        base = "server"
    sid = base
    i = 2
    while sid in _servers:
        sid = f"{base}-{i}"
        i += 1
    return sid


def create_server(name, jar_type="vanilla", min_ram="512M", max_ram="2G",
                  port=None, mc_version=None):
    sid = _gen_id(name)
    server_dir = SERVERS_BASE / sid
    server_dir.mkdir(parents=True, exist_ok=True)
    if port is None:
        port = _next_available_port()
    inst = ServerInstance(sid, name, server_dir, jar_type, min_ram, max_ram, port)
    inst.save_config()
    with _registry_lock:
        _servers[sid] = inst
    _save_registry()
    return inst


def delete_server(sid):
    inst = _servers.get(sid)
    if not inst:
        return False, "Server not found."
    if inst.is_running():
        return False, "Stop the server before deleting."
    with _registry_lock:
        del _servers[sid]
    _save_registry()
    import shutil
    if inst.dir.exists():
        shutil.rmtree(str(inst.dir), ignore_errors=True)
    return True, f"Deleted server '{inst.name}'"


def import_server(folder_path, name=None):
    folder = Path(folder_path).resolve()
    if not folder.is_dir():
        return None, "Folder does not exist."
    if name is None:
        name = folder.name
    sid = _gen_id(name)
    port = _next_available_port()
    jar_type = _detect_jar_type(folder)
    dest = SERVERS_BASE / sid
    if str(folder.resolve()) != str(dest.resolve()):
        import shutil
        shutil.copytree(str(folder), str(dest), dirs_exist_ok=True, ignore_dangling_symlinks=True)
    else:
        dest = folder
    inst = ServerInstance(sid, name, dest, jar_type, port=port)
    inst.load_config()
    with _registry_lock:
        _servers[sid] = inst
    _save_registry()
    return inst, f"Imported '{name}' to mc-servers/{sid}"


def _detect_jar_type(folder):
    for f in folder.glob("*.jar"):
        fname = f.name.lower()
        if "paper" in fname: return "paper"
        if "purpur" in fname: return "purpur"
        if "spigot" in fname: return "spigot"
        if "forge" in fname: return "forge"
        if "fabric" in fname: return "fabric"
        if "neoforge" in fname: return "neoforge"
        if "quilt" in fname: return "quilt"
        if "folia" in fname: return "folia"
        return "vanilla"
    return "unknown"


def _next_available_port():
    used = set()
    for s in _servers.values():
        used.add(s.port)
    port = 25565
    while port in used:
        port += 1
    return port


def _save_registry():
    data = []
    for s in _servers.values():
        d = s.to_dict()
        data.append({
            "id": d["id"], "name": d["name"], "dir": d["dir"],
            "jar_type": d["jar_type"], "min_ram": s.min_ram,
            "max_ram": s.max_ram, "port": s.port,
        })
    try:
        REGISTRY_PATH.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


def load_registry():
    SERVERS_BASE.mkdir(parents=True, exist_ok=True)
    if REGISTRY_PATH.exists():
        try:
            data = json.loads(REGISTRY_PATH.read_text())
            for item in data:
                sid = item.get("id", "")
                if not sid or sid in _servers:
                    continue
                sdir = Path(item.get("dir", str(SERVERS_BASE / sid)))
                if not sdir.exists():
                    continue
                inst = ServerInstance(
                    sid, item.get("name", sid), sdir,
                    item.get("jar_type", "vanilla"),
                    item.get("min_ram", "512M"),
                    item.get("max_ram", "2G"),
                    item.get("port", 25565),
                )
                inst.load_config()
                with _registry_lock:
                    _servers[sid] = inst
        except Exception:
            pass
    for d in SERVERS_BASE.iterdir():
        if not d.is_dir():
            continue
        sid = d.name
        if sid in _servers:
            continue
        has_jar = any(d.glob("*.jar"))
        if not has_jar:
            continue
        inst = ServerInstance(sid, sid, d)
        inst.load_config()
        with _registry_lock:
            _servers[sid] = inst
    _save_registry()

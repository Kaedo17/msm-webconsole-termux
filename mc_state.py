"""Shared state and config persistence for the Minecraft web console.

All modules access global state via this module.  Because mutable globals
(server_proc, console_history, etc.) are reassigned at runtime, always
reference them as ``mc_state.server_proc`` rather than importing the name,
so you always see the latest value.
"""

import json
import os
import queue
import shutil
import threading
from pathlib import Path

# ── Paths & constants ────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
SERVER_DIR = Path(os.environ.get("SERVER_DIR", SCRIPT_DIR))
HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT", 5000))
JAVA_BIN = shutil.which("java") or "java"
JAR_NAME = os.environ.get("SERVER_JAR", "server.jar")

# ── Global runtime state ─────────────────────────────────────────────
server_proc = None
console_history = []
console_queue = queue.Queue()
status_cache = {"online": False, "players": [], "tps": 0, "uptime": 0, "mem_mb": 0, "started_at": ""}
_status_lock = threading.Lock()
CONSOLE_MAX = 500

MIN_RAM = os.environ.get("MIN_RAM", "512M")
MAX_RAM = os.environ.get("MAX_RAM", "2G")


def get_status_lock():
    return _status_lock


# ── Config persistence ───────────────────────────────────────────────

def _config_path():
    return SERVER_DIR / ".webconsole.json"


def load_config():
    global MIN_RAM, MAX_RAM
    path = _config_path()
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text())
        MIN_RAM = data.get("min_ram", MIN_RAM)
        MAX_RAM = data.get("max_ram", MAX_RAM)
    except Exception:
        pass


def save_config():
    path = _config_path()
    try:
        existing = {}
        if path.exists():
            try:
                existing = json.loads(path.read_text())
            except Exception:
                pass
        existing["min_ram"] = MIN_RAM
        existing["max_ram"] = MAX_RAM
        path.write_text(json.dumps(existing, indent=2))
    except Exception:
        pass
